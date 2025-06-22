import os
import numpy as np
from osgeo import gdal, ogr, osr
from glob import glob
from tqdm import tqdm
from PIL import Image
import cv2
from datetime import datetime

gdal.UseExceptions()

def wkt_polygon_to_pixel_coords(wkt_polygon, dataset):
    """
    Given a WKT polygon (EPSG:4326) and an open GDAL dataset (EPSG:32619),
    return its boundary in pixel coords.
    """
    geom = ogr.CreateGeometryFromWkt(wkt_polygon)
    if geom is None:
        raise ValueError("Invalid WKT polygon.")

    # Set up coordinate transform 4326→32619
    src = osr.SpatialReference(); src.ImportFromEPSG(4326)
    tgt = osr.SpatialReference(); tgt.ImportFromEPSG(32619)
    geom.Transform(osr.CoordinateTransformation(src, tgt))

    gt = dataset.GetGeoTransform()
    def world_to_pixel(x, y):
        col = int(round((x - gt[0]) / gt[1]))
        row = int(round((y - gt[3]) / gt[5]))
        return col, row

    ring = geom.GetGeometryRef(0)
    coords = [world_to_pixel(*ring.GetPoint(i)[:2]) for i in range(ring.GetPointCount())]
    return coords

def _draw_polygon_on_array(img, pixel_coords, color=255, thickness=3):
    """Draw polygon edges (thickness px) on a 2D numpy array."""
    def draw_line(arr, x0, y0, x1, y1):
        dx, dy = abs(x1-x0), abs(y1-y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        x, y = x0, y0
        while True:
            _fill(arr, x, y)
            if x == x1 and y == y1: break
            e2 = 2*err
            if e2 > -dy:
                err -= dy; x += sx
            if e2 < dx:
                err += dx; y += sy

    def _fill(arr, cx, cy):
        r = thickness//2 if thickness>2 else thickness
        for rx in range(cx-r, cx+r+1):
            for ry in range(cy-r, cy+r+1):
                if 0 <= ry < arr.shape[0] and 0 <= rx < arr.shape[1]:
                    arr[ry, rx] = color

    for (x0, y0), (x1, y1) in zip(pixel_coords, pixel_coords[1:]):
       draw_line(img, x0, y0, x1, y1)

def parse_filename_for_datetime(filename):
    """
    Extract a datetime and identifier from a Sentinel-1 style filename.
    Example: "S1A_..._20170101T072022_..._B670_SNAP.png"
    """
    try:
        year = filename[17:21]
        month = filename[21:23]
        day = filename[23:25]
        hour = filename[26:28]
        minute = filename[28:30]
        second = filename[30:32]
        sat = filename[0:3]
        dt = datetime(int(year), int(month), int(day),
                      int(hour), int(minute), int(second))
    except Exception:
        dt = datetime.min
        sat = "SAT"
    return dt, sat

def get_date_from_filename(filename):
    """Return only the date part of the datetime parsed from filename."""
    dt, _ = parse_filename_for_datetime(filename)
    return dt.date() if dt != datetime.min else None

def convert_geotiffs_to_pngs(
    input_dir,
    output_dir,
    desired_width,
    desired_height,
    vmin,
    vmax,
    channel_num=1,
    flag_calc_vmin_vmax=False,
    num_processes=1,       # ignored, kept for signature
    polygon_wkt=None,
    landmask_path=None
):
    """
    Converts all .tif in input_dir → .png in output_dir.
    Border pixels inherit from previous frame instead of median.
    """
    os.makedirs(output_dir, exist_ok=True)
    files = glob(os.path.join(input_dir, "*.tif"))
    if not files:
        print("[Info] No GeoTIFFs found.")
        return

    # load landmask if requested
    landmask = None
    if landmask_path:
        lm_ds = gdal.Open(landmask_path)
        if lm_ds is None:
            print("[Error] Can't open landmask; skipping mask.")
        else:
            landmask = lm_ds.GetRasterBand(1).ReadAsArray()[:desired_height, :desired_width]
            lm_ds = None

    # optionally compute vmin/vmax over the series
    if flag_calc_vmin_vmax:
        vals = []
        print("[Info] Computing percentiles...")
        for fp in tqdm(files, desc="Stats"):
            ds = gdal.Open(fp)
            if ds is None: continue
            d = ds.GetRasterBand(channel_num).ReadAsArray()[:desired_height, :desired_width]
            ds = None
            if landmask is not None:
                mask = (~np.isnan(d)) & (landmask == 1)
            else:
                mask = ~np.isnan(d)
            vals.append(d[mask])
        vals = np.concatenate(vals) if vals else np.array([])
        if vals.size:
            low, high = 0.135, 99.865
            vmin = np.percentile(vals, low)
            vmax = np.percentile(vals, high)
            print(f"[Info] New vmin={vmin}, vmax={vmax}")
        else:
            print("[Error] No data for vmin/vmax.")
            return

    # sort files chronologically
    files.sort(key=lambda fp: parse_filename_for_datetime(os.path.basename(fp))[0])

    prev_out = None
    print("[Info] Starting conversion...")
    for fp in tqdm(files, desc="Converting"):
        fn = os.path.basename(fp)
        out_png = os.path.join(output_dir, os.path.splitext(fn)[0] + ".png")

        ds = gdal.Open(fp)
        if ds is None:
            print(f"[Warn] Cannot open {fn}")
            continue

        data = ds.GetRasterBand(channel_num).ReadAsArray()[:desired_height, :desired_width]
        ds = None

        # landmask logic
        if landmask is not None:
            lm = (landmask == 1)
        else:
            lm = np.zeros_like(data, dtype=bool)

        # masks
        border_mask = np.isnan(data) & (~lm)
        ocean_mask = (~np.isnan(data)) & (~lm)

        # prepare output
        out = np.zeros_like(data, dtype=np.uint8)

        # ocean stretch
        oce = data[ocean_mask]
        if oce.size == 0:
            print(f"[Warn] No ocean pixels in {fn}")
            continue
        oce_clip = np.clip(oce, vmin, vmax)
        oce_norm = ((oce_clip - vmin)/(vmax-vmin)*255).astype(np.uint8)
        out[ocean_mask] = oce_norm

        # border pixels: inherit from previous frame if available
        if prev_out is None:
            bv = np.median(oce)
            bvn = int(((np.clip(bv, vmin, vmax) - vmin)/(vmax-vmin))*255)
            out[border_mask] = bvn
        else:
            out[border_mask] = prev_out[border_mask]

        # optional polygon overlay
        if polygon_wkt:
            pix = wkt_polygon_to_pixel_coords(polygon_wkt, gdal.Open(fp))
            _draw_polygon_on_array(out, pix, color=255, thickness=5)

        # save PNG
        Image.fromarray(out, mode="L").save(out_png)

        # remember for next
        prev_out = out.copy()

    print("[Info] Done.")

def add_text_to_image(image,
                        date_text,
                        time_text,
                        identifier_text,
                        position=(20, 30),
                        font_scale=1.0,
                        base_thickness=2,
                        base_spacing=30):
    """
    Add date, time, and identifier text to the image with scalable font,
    thickness, and vertical offsets.
    """

    font = cv2.FONT_HERSHEY_SIMPLEX

    # Scale starting position, thickness, and line spacing
    x = int(position[0] * font_scale)
    y = int(position[1] * font_scale)
    thickness = max(int(base_thickness * font_scale), 1)
    spacing = int(base_spacing * font_scale)
    color = (0, 0, 0)  # black

    # Compute positions for each line
    date_pos = (x, y)
    time_pos = (x, y + spacing)
    id_pos   = (x, y + 2 * spacing)

    # Draw text
    cv2.putText(image, date_text, date_pos, font,
                font_scale, color, thickness, cv2.LINE_AA)
    cv2.putText(image, time_text, time_pos, font,
                font_scale, color, thickness, cv2.LINE_AA)
    cv2.putText(image, identifier_text, id_pos, font,
                font_scale, color, thickness, cv2.LINE_AA)

    return image


def create_video(dir1,
                 output_video,
                 frame_rate=3,
                 side_by_side=False,
                 dir2=None,
                 start_date_str=None,
                 end_date_str=None):
    """
    Creates an MP4 timelapse from PNGs, with optional date filtering
    and side-by-side mode.
    """
    # parse date filters
    start_date = None
    end_date = None
    date_filter = False
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%d%m%Y").date()
            date_filter = True
        except ValueError:
            print(f"Invalid start_date '{start_date_str}'")
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, "%d%m%Y").date()
            date_filter = True
        except ValueError:
            print(f"Invalid end_date '{end_date_str}'")

    def filter_list(lst):
        if not date_filter:
            return lst
        out = []
        for f in lst:
            d = get_date_from_filename(f)
            if d is None: continue
            if start_date and d < start_date: continue
            if end_date and d > end_date:   continue
            out.append(f)
        return out

    if side_by_side:
        if dir2 is None:
            raise ValueError("dir2 must be provided for side_by_side=True")
        imgs1 = [f for f in os.listdir(dir1) if f.lower().endswith('.png')]
        imgs2 = [f for f in os.listdir(dir2) if f.lower().endswith('.png')]
        imgs1 = filter_list(imgs1)
        imgs2 = filter_list(imgs2)
        common = sorted(set(imgs1) & set(imgs2),
                        key=lambda f: parse_filename_for_datetime(f)[0])
        if not common:
            print("No common images to make video.")
            return

        # determine size
        im1 = cv2.imread(os.path.join(dir1, common[0]))
        im2 = cv2.imread(os.path.join(dir2, common[0]))
        if im1.shape[:2] != im2.shape[:2]:
            im2 = cv2.resize(im2, (im1.shape[1], im1.shape[0]), interpolation=cv2.INTER_AREA)
        h, w = im1.shape[:2]
        out_h, out_w = h, w*2

        writer = cv2.VideoWriter(output_video,
                                 cv2.VideoWriter_fourcc(*'mp4v'),
                                 frame_rate,
                                 (out_w, out_h))

        for fname in common:
            i1 = cv2.imread(os.path.join(dir1, fname))
            i2 = cv2.imread(os.path.join(dir2, fname))
            i2 = cv2.resize(i2, (w, h), interpolation=cv2.INTER_AREA)
            combined = np.hstack([i1, i2])
            dt, sat = parse_filename_for_datetime(fname)
            date_str = dt.strftime("%d/%m/%Y")
            time_str = dt.strftime("%H:%M:%S")
            frame = add_text_to_image(combined, date_str, time_str, sat)
            writer.write(frame)
        writer.release()
        print(f"Side-by-side video saved to {output_video}")

    else:
        imgs = [f for f in os.listdir(dir1) if f.lower().endswith('.png')]
        imgs = filter_list(imgs)
        imgs = sorted(imgs, key=lambda f: parse_filename_for_datetime(f)[0])
        if not imgs:
            print("No images to make video.")
            return

        first = cv2.imread(os.path.join(dir1, imgs[0]))
        h, w = first.shape[:2]
        writer = cv2.VideoWriter(output_video,
                                 cv2.VideoWriter_fourcc(*'mp4v'),
                                 frame_rate,
                                 (w, h))

        for fname in imgs:
            img = cv2.imread(os.path.join(dir1, fname))
            if img.shape[:2] != (h, w):
                img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
            dt, sat = parse_filename_for_datetime(fname)
            date_str = dt.strftime("%d/%m/%Y")
            time_str = dt.strftime("%H:%M:%S")
            frame = add_text_to_image(img, date_str, time_str, sat)
            writer.write(frame)
        writer.release()
        print(f"Single-directory timelapse saved to {output_video}")

if __name__ == "__main__":
    # convert_geotiffs_to_pngs(
    #     input_dir='/mnt/d/data_2/output/pituffik_20_21/geotiffs_subset_base_padded/',
    #     output_dir='/mnt/d/data_2/output/pituffik_20_21/pngs/HH_subset_base_padded/',
    #     desired_width=3708,
    #     desired_height=2015,
    #     vmin=-42,
    #     vmax=-0.1,
    #     channel_num=1,
    #     flag_calc_vmin_vmax=True,
    #     polygon_wkt=None,
    #     landmask_path=None
    # ) 

    create_video(
        dir1='/mnt/d/data_2/output/pituffik_20_21/pngs/HH_subset_base_padded/',
        output_video='/mnt/d/data_2/output/pituffik_20_21/pituffik_20_21_subset_base.mp4',
        frame_rate=3,
        side_by_side=False,
        start_date_str=None,
        end_date_str=None
    )
