#!/usr/bin/env python3
import os
import math
import numpy as np
import rasterio
from affine import Affine
import argparse


def scan_geotiffs(input_dir, expected_res=40.0, tol=1e-6):
    """
    Scan all .tif files in input_dir, collect their resolutions and bounds,
    and verify they match expected_res within tolerance.
    """
    infos = []
    for fname in os.listdir(input_dir):
        if not fname.lower().endswith('.tif'):
            continue
        path = os.path.join(input_dir, fname)
        with rasterio.open(path) as src:
            res_x, res_y = src.res
            if abs(abs(res_x) - expected_res) > tol or abs(abs(res_y) - expected_res) > tol:
                print(f"Warning: {fname} resolution {src.res} differs from expected {expected_res}")
            bounds = src.bounds
            infos.append({
                'path': path,
                'width': src.width,
                'height': src.height,
                'bounds': bounds
            })
    if not infos:
        raise ValueError(f"No GeoTIFFs found in {input_dir}")
    return infos


def build_reference_grid(infos, resolution=40.0):
    """
    Compute a shared bounding box snapped to the grid, and produce Affine and output size.
    """
    lefts   = [info['bounds'].left   for info in infos]
    rights  = [info['bounds'].right  for info in infos]
    bottoms = [info['bounds'].bottom for info in infos]
    tops    = [info['bounds'].top    for info in infos]

    min_left   = min(lefts)
    max_right  = max(rights)
    min_bottom = min(bottoms)
    max_top    = max(tops)

    # Snap to grid
    grid = resolution
    min_left   = math.floor(min_left   / grid) * grid
    max_top    = math.ceil (max_top    / grid) * grid
    max_right  = math.ceil (max_right  / grid) * grid
    min_bottom = math.floor(min_bottom / grid) * grid

    # Compute pixel dimensions
    target_width  = int(round((max_right  - min_left)   / grid))
    target_height = int(round((max_top    - min_bottom) / grid))

    # Build Affine
    ref_transform = Affine(grid, 0.0, min_left,
                            0.0, -grid, max_top)

    return ref_transform, (target_width, target_height)


def pad_to_ref(src_path, dst_path, ref_transform, target_size, nodata):
    """
    Pad or crop a single raster to the reference grid, writing full-size raster to dst_path.
    """
    with rasterio.open(src_path) as src:
        data = src.read()
        tw, th = target_size
        left, bottom, right, top = src.bounds
        px, py = abs(src.res[0]), abs(src.res[1])
        ref_left, ref_top = ref_transform.c, ref_transform.f

        col_off = (left   - ref_left) / px
        row_off = (ref_top - top    ) / py
        col_i   = int(math.floor(col_off))
        row_i   = int(math.floor(row_off))

        dst_col_start = max(col_i, 0)
        dst_row_start = max(row_i, 0)
        dst_col_end   = min(col_i + src.width,  tw)
        dst_row_end   = min(row_i + src.height, th)

        src_col_start = max(0, -col_i)
        src_row_start = max(0, -row_i)
        src_col_end   = src_col_start + (dst_col_end - dst_col_start)
        src_row_end   = src_row_start + (dst_row_end - dst_row_start)

        out = np.full((src.count, th, tw), nodata, dtype=data.dtype)
        out[:, dst_row_start:dst_row_end,
               dst_col_start:dst_col_end] = \
            data[:, src_row_start:src_row_end,
                 src_col_start:src_col_end]

        profile = src.profile.copy()
        profile.update({
            'width':     tw,
            'height':    th,
            'transform': ref_transform,
            'nodata':    nodata
        })

        with rasterio.open(dst_path, 'w', **profile) as dst:
            dst.write(out)


def pad_directory(input_dir, output_dir, resolution=40.0, nodata=np.nan):
    """
    Full pipeline: scan, build grid, then pad/crop all images into output_dir.
    """
    infos = scan_geotiffs(input_dir, expected_res=resolution)
    ref_transform, target_size = build_reference_grid(infos, resolution)
    os.makedirs(output_dir, exist_ok=True)
    for info in infos:
        fname = os.path.basename(info['path'])
        dst = os.path.join(output_dir, fname)
        pad_to_ref(info['path'], dst, ref_transform, target_size, nodata)
        print(f"Processed: {fname}")
    print(f"All done. Output grid size: {target_size}, transform: {ref_transform}")


## Example usage:
"""
python pad_images_grid_alignment.py \
  --input-dir /path/to/geotiffs \
  --output-dir /path/to/aligned_geotiffs
"""


def main():
    parser = argparse.ArgumentParser(
        description='Pad/crop GeoTIFFs to a common grid.'
    )
    parser.add_argument('-i', '--input-dir', required=True,
                        help='Directory of input GeoTIFFs')
    parser.add_argument('-o', '--output-dir',
                        help='Directory for output files (required unless --in-place)')
    parser.add_argument('-r', '--resolution', type=float, default=40.0,
                        help='Grid resolution in map units (default: 40)')
    parser.add_argument('--nodata', type=float, default=float('nan'),
                        help='NoData value for padding (default: NaN)')
    parser.add_argument('--in-place', action='store_true',
                        help='Overwrite all files in the input directory')
    args = parser.parse_args()

    if args.in_place:
        if args.output_dir:
            parser.error('--output-dir must not be set when using --in-place')
        pad_directory(args.input_dir, args.input_dir,
                      resolution=args.resolution,
                      nodata=args.nodata)
    else:
        if not args.output_dir:
            parser.error('--output-dir is required when not using --in-place')
        pad_directory(args.input_dir, args.output_dir,
                      resolution=args.resolution,
                      nodata=args.nodata)

if __name__ == '__main__':
    main()
