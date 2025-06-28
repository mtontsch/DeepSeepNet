#!/usr/bin/env python3
"""
geotiff_video_maker.py: Combine subsetting, padding, PNG conversion, and video creation
from SNAP output into one utility, with improved regridding to maintain sub-pixel alignment.

Features:
- Optional GeoTIFF subsetting by WKT
- Padding/regridding via GDAL Warp with user-specified resampling (nearest, bilinear, cubic, lanczos)
- Consistent orthorectification using a DEM
- PNG conversion with auto or user vmin/vmax
- Landmask support
- Timestamp overlay on video frames, including Satellite ID, date, and time in one line at user-chosen position
- Cleans up intermediate files by default
"""

import os                      # OS routines for file operations
import argparse                # Parse command-line arguments
import shutil                  # High-level file operations (cleanup)
import numpy as np            # Numerical operations on arrays
from glob import glob          # Filename pattern matching
from osgeo import gdal        # GDAL for geospatial data handling
from tqdm import tqdm          # Progress bars for loops
from affine import Affine      # Affine transformation for georeferencing
from datetime import datetime  # Date/time parsing and handling
import cv2                     # OpenCV for image and video processing
from PIL import Image          # PIL for image I/O

gdal.UseExceptions()          # Enable GDAL exceptions for error handling

# ------ Subset GeoTIFFs by WKT ------
def subset_geotiff_by_wkt(input_dir, output_dir, wkt_polygon,
                           src_srs_epsg=4326, crop_to_cutline=True):
    """
    Crop all GeoTIFFs in input_dir to the provided WKT polygon and save to output_dir.
    """
    os.makedirs(output_dir, exist_ok=True)  # Ensure output directory exists
    for src in glob(os.path.join(input_dir, '*.tif')):
        dst = os.path.join(output_dir, os.path.basename(src))
        # Prepare warp options for GDAL Warp
        opts = gdal.WarpOptions(
            cutlineWKT=wkt_polygon,
            cutlineSRS=f"EPSG:{src_srs_epsg}",
            cropToCutline=crop_to_cutline,
            dstNodata=None,
            format='GTiff'
        )
        gdal.Warp(dst, src, options=opts)  # Perform the subset operation
    print(f"[Info] Subsetting done: {len(os.listdir(output_dir))} files")


# ------ Build reference grid extents ------
def build_reference_grid(infos, resolution):
    """
    Compute a common output grid extent and transform from a list of bounding boxes.
    Ensures sub-pixel alignment by snapping to the specified resolution.
    """
    # Unpack bounds lists
    lefts, rights, bottoms, tops = zip(*[
        (b.left, b.right, b.bottom, b.top) for b in infos
    ])
    # Snap extents to resolution grid
    min_left = resolution * (min(lefts) // resolution)
    max_right = resolution * -(-max(rights) // resolution)
    min_bottom = resolution * (min(bottoms) // resolution)
    max_top = resolution * -(-max(tops) // resolution)
    # Compute output dimensions
    width = int((max_right - min_left) / resolution)
    height = int((max_top - min_bottom) / resolution)
    # Affine transform for output grid
    transform = Affine(resolution, 0, min_left,
                       0, -resolution, max_top)
    return (min_left, min_bottom, max_right, max_top), transform, (width, height)


# ------ Pad/Regrid GeoTIFFs with GDAL Warp ------
def pad_directory(input_dir, output_dir, resolution=40.0,
                  nodata=None, resampling='cubic'):
    """
    Reproject and pad all GeoTIFFs in input_dir to a common grid, saving results to output_dir.
    """
    os.makedirs(output_dir, exist_ok=True)
    infos = []
    # Gather bounds and paths
    for fn in glob(os.path.join(input_dir, '*.tif')):
        ds = gdal.Open(fn)
        if not ds:
            continue
        gt = ds.GetGeoTransform()
        xsz, ysz = ds.RasterXSize, ds.RasterYSize
        bounds = (gt[0], gt[3] + gt[5]*ysz,
                  gt[0] + gt[1]*xsz, gt[3])
        infos.append({'bounds': bounds, 'path': fn})
        ds = None
    if not infos:
        raise RuntimeError(f"No TIFFs in {input_dir}")
    # Build common grid
    ext, transform, size = build_reference_grid(
        [type('B', (), {'left': b[0], 'bottom': b[1],
                        'right': b[2], 'top': b[3]})
         for b in [i['bounds'] for i in infos]], resolution)
    min_left, min_bottom, max_right, max_top = ext

    # GDAL Warp options for padding/regridding
    warp_opts = gdal.WarpOptions(
        format='GTiff',
        outputBounds=(min_left, min_bottom, max_right, max_top),
        xRes=resolution, yRes=resolution,
        resampleAlg=resampling,
        srcNodata=nodata, dstNodata=nodata,
        multithread=True
    )
    # Apply warp to each file
    for info in infos:
        src = info['path']
        dst = os.path.join(output_dir, os.path.basename(src))
        gdal.Warp(dst, src, options=warp_opts)
    print(f"[Info] Regridded {len(infos)} files to grid {size} with '{resampling}' resampling")
    return transform, size


# ------ Parse datetime & Satellite ID from filename ------
def parse_filename_for_datetime(fn):
    """
    Extract datetime from filename at fixed positions; fallback to min datetime on error.
    """
    try:
        y, mo, d = fn[17:21], fn[21:23], fn[23:25]
        hh, mi, ss = fn[26:28], fn[28:30], fn[30:32]
        return datetime(int(y), int(mo), int(d), int(hh), int(mi), int(ss))
    except Exception:
        return datetime.min


def parse_filename_for_satid(fn):
    """
    Extract Satellite ID from filename (assumes prefix before underscore).
    """
    return os.path.basename(fn).split('_')[0]


# ------ Overlay text on image frame ------
def overlay_text(img, text, font_scale, pos):
    """
    Draw a black-outline white text on img at position pos.
    """
    thickness = max(1, int(font_scale * 2))
    # Draw outline (thicker black)
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX,
                font_scale, (0, 0, 0), thickness+2, cv2.LINE_AA)
    # Draw main text (white)
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX,
                font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
    return img


# ------ Convert padded GeoTIFFs to PNGs ------
def convert_geotiffs_to_pngs(input_dir, output_dir, size,
                              vmin=None, vmax=None, channel=1,
                              landmask_path=None):
    """
    Convert all GeoTIFFs in input_dir to grayscale PNGs using linear scaling.
    Supports auto or user-defined vmin/vmax and optional landmask.
    """
    w, h = size
    os.makedirs(output_dir, exist_ok=True)
    # Sort files by parsed datetime
    files = sorted(glob(os.path.join(input_dir, '*.tif')),
                   key=lambda x: parse_filename_for_datetime(os.path.basename(x)))

    # Load landmask if provided
    lm = None
    if landmask_path:
        ds = gdal.Open(landmask_path)
        if ds:
            lm = ds.GetRasterBand(1).ReadAsArray()[:h, :w]
            ds = None

    # Determine vmin/vmax if not specified
    if vmin is None or vmax is None:
        vals = []
        print("[Info] Computing vmin/vmax from data...")
        for fp in tqdm(files, desc='Stats'):
            ds = gdal.Open(fp)
            arr = ds.GetRasterBand(channel).ReadAsArray()[:h, :w]
            ds = None
            mask = (~np.isnan(arr)) if lm is None else ((~np.isnan(arr)) & (lm == 1))
            if np.any(mask):
                vals.append(arr[mask])
        if not vals:
            raise RuntimeError("No valid data for vmin/vmax calculation.")
        all_vals = np.concatenate(vals)
        # Clip extreme percentiles for contrast
        vmin_calc, vmax_calc = np.percentile(all_vals, [0.135, 99.865])
        vmin, vmax = vmin_calc, vmax_calc
        print(f"[Info] Computed vmin={vmin:.3f}, vmax={vmax:.3f}")
    else:
        print(f"[Info] Using user-specified vmin={vmin}, vmax={vmax}")

    prev = None
    # Process each file to PNG
    for fp in tqdm(files, desc='Convert to PNG'):
        fn = os.path.basename(fp)
        ds = gdal.Open(fp)
        arr = ds.GetRasterBand(channel).ReadAsArray()[:h, :w]
        ds = None
        # Masks for ocean and no-data
        mask_o = (~np.isnan(arr)) & ((lm is None) | (lm == 0))
        mask_b = np.isnan(arr) & ((lm is None) | (lm == 0))
        out = np.zeros((h, w), np.uint8)
        valid = arr[mask_o]
        clip = np.clip(valid, vmin, vmax)
        norm = ((clip - vmin) / (vmax - vmin) * 255).astype(np.uint8)
        out[mask_o] = norm
        # Fill background/no-data with previous frame or median border
        if prev is None:
            border = int(((np.clip(np.median(valid) if valid.size else 0,
                                     vmin, vmax) - vmin) / (vmax - vmin)) * 255)
            out[mask_b] = border
        else:
            out[mask_b] = prev[mask_b]
        prev = out.copy()
        # Save as 8-bit grayscale PNG
        Image.fromarray(out, 'L').save(os.path.join(output_dir, fn.replace('.tif', '.png')))
    print(f"[Info] PNGs written: {len(files)}")


# ------ Create MP4 from PNGs with timestamp overlay ------
def create_video(png_dir, output_dir, timeseries_id, frame_rate=3,
                 start_date=None, end_date=None,
                 text_size=None, text_position='bottom-left'):
    """
    Assemble PNG frames into an MP4, overlaying timestamp and satellite ID on each frame.
    Can filter frames by date range.
    """
    # Collect and sort frame filenames
    pngs = sorted([f for f in os.listdir(png_dir) if f.lower().endswith('.png')],
                  key=lambda f: parse_filename_for_datetime(f))
    # Filter by start/end dates if given
    if start_date:
        sd = datetime.strptime(start_date, '%d%m%Y').date()
        pngs = [f for f in pngs if parse_filename_for_datetime(f).date() >= sd]
    if end_date:
        ed = datetime.strptime(end_date, '%d%m%Y').date()
        pngs = [f for f in pngs if parse_filename_for_datetime(f).date() <= ed]
    if not pngs:
        print("[Error] No frames to make video.")
        return
    # Initialize video writer based on first frame size
    frame0 = cv2.imread(os.path.join(png_dir, pngs[0]))
    h, w = frame0.shape[:2]
    # Create video filename using the timeseries ID
    video_filename = f"{timeseries_id}_timeseries.mp4"
    video_path = os.path.join(output_dir, video_filename)
    vw = cv2.VideoWriter(video_path,
                        cv2.VideoWriter_fourcc(*'mp4v'),
                        frame_rate, (w, h))
    # Write each frame with optional text overlay
    for fn in tqdm(pngs, desc='Video'):
        img = cv2.imread(os.path.join(png_dir, fn))
        if text_size and text_position != 'none':
            ts = parse_filename_for_datetime(fn).strftime('%d.%m.%Y %H:%M:%S')
            sat = parse_filename_for_satid(fn)
            text = f"{sat} {ts}"
            margin = int(10 * text_size)
            # Determine text position on frame
            (text_w, text_h), _ = cv2.getTextSize(text,
                                                  cv2.FONT_HERSHEY_SIMPLEX,
                                                  text_size,
                                                  max(1, int(text_size * 2)))
            if text_position == 'top-left':
                pos = (margin, margin + text_h)
            else:  # bottom-left
                pos = (margin, h - margin)
            img = overlay_text(img, text, text_size, pos)
        vw.write(img)
    vw.release()  # Finalize and save video
    print(f"[Info] Video saved to {video_path}")


# ------ Main entrypoint ------
def main():
    # Command-line interface setup
    p = argparse.ArgumentParser(description='Make timelapse from GeoTIFFs')
    p.add_argument('-i', '--input-dir', required=True,
                   help='Directory with input GeoTIFFs')
    p.add_argument('-o', '--output-dir', required=True,
                   help='Directory with output data')
    p.add_argument('-id', '--timeseries-id', required=True,
                   help='ID for the time series')
    p.add_argument('-w', '--wkt-polygon', default=None,
                   help='WKT string to subset GeoTIFFs')
    p.add_argument('--src-srs-epsg', type=int, default=4326,
                   help='EPSG code of input GeoTIFFs')
    p.add_argument('--resolution', type=float, default=40.0,
                   help='Output grid resolution (meters)')
    p.add_argument('--nodata', type=float, default=float('nan'),
                   help='NoData value for warping')
    p.add_argument('--channel', type=int, default=1,
                   help='Raster band to use for PNG conversion')
    p.add_argument('--vmin', type=float, default=None,
                   help='Minimum value for scaling')
    p.add_argument('--vmax', type=float, default=None,
                   help='Maximum value for scaling')
    p.add_argument('--landmask', default=None,
                   help='Path to landmask GeoTIFF')
    p.add_argument('--frame-rate', type=int, default=3,
                   help='Frame rate for output video')
    p.add_argument('--start-date', default=None,
                   help='Filter start date (DDMMYYYY)')
    p.add_argument('--end-date', default=None,
                   help='Filter end date (DDMMYYYY)')
    p.add_argument('--text-size', type=float, default=None,
                   help='Font scale for timestamp overlay')
    p.add_argument('--text-position', choices=['top-left','bottom-left','none'],
                   default='bottom-left',
                   help='Position for timestamp overlay')
    p.add_argument('--keep-intermediate', action='store_true',
                   help='Keep intermediate files')
    args = p.parse_args()

    # Data directories setup
    os.makedirs(args.output_dir, exist_ok=True)
    base = args.output_dir
    print(f"[Info] Base output directory: {base}")

    intermediate_dir = os.path.join(base, f'intermediate_{args.timeseries_id}')
    os.makedirs(intermediate_dir, exist_ok=True)

    subset_dir = os.path.join(intermediate_dir, 'subset') if args.wkt_polygon else None
    pad_dir = os.path.join(intermediate_dir, 'padded')
    png_dir = os.path.join(intermediate_dir, 'pngs')
    inp = args.input_dir

    # Optional subsetting step
    if args.wkt_polygon:
        print("[Step] Subsetting GeoTIFFs...")
        subset_geotiff_by_wkt(inp, subset_dir,
                               args.wkt_polygon, args.src_srs_epsg)
        inp = subset_dir

    # Padding/regridding step
    print(f"[Step] Padding GeoTIFFs to {pad_dir}...")
    _, size = pad_directory(inp, pad_dir,
                             args.resolution, args.nodata)

    # PNG conversion step
    print(f"[Step] Converting to PNGs {size}...")
    convert_geotiffs_to_pngs(pad_dir, png_dir, size,
                              args.vmin, args.vmax,
                              args.channel, args.landmask)

    # Video creation step
    print("[Step] Creating MP4...")
    create_video(png_dir, args.output_dir, args.timeseries_id,
                frame_rate=args.frame_rate,
                start_date=args.start_date,
                end_date=args.end_date,
                text_size=args.text_size,
                text_position=args.text_position)

    # Cleanup or keep intermediates
    if args.keep_intermediate:
        print(f"[Done] Intermediates at {base}")
    else:
        shutil.rmtree(intermediate_dir)
        print("[Done] Cleaned up intermediates.")

if __name__ == '__main__':
    main()
