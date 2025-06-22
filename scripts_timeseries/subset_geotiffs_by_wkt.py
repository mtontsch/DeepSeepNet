import os
import sys
from glob import glob
from osgeo import gdal

gdal.UseExceptions()

def subset_geotiff_by_wkt(input_dir, output_dir, wkt_polygon,
                           src_srs_epsg=4326,
                           crop_to_cutline=True, overwrite=False):
    """
    Subset all GeoTIFF files in input_dir by a WKT polygon.

    This function works on GeoTIFFs in any projection (including any UTM zone).
    GDAL will read each raster's CRS from its metadata and automatically
    reproject the provided WKT cutline (given in src_srs_epsg) into the
    raster's native CRS before cropping.

    :param input_dir: Directory containing source GeoTIFFs.
    :param output_dir: Directory to write subsetted GeoTIFFs.
    :param wkt_polygon: WKT string defining the cutline polygon (assumed lon/lat WGS84 by default).
    :param src_srs_epsg: EPSG code of WKT polygon (default 4326 for WGS84 lon/lat).
    :param crop_to_cutline: If True, crop output to cutline extent.
    :param overwrite: If True, overwrite existing output files.
    """
    os.makedirs(output_dir, exist_ok=True)
    tif_paths = glob(os.path.join(input_dir, '*.tif'))
    if not tif_paths:
        print(f"No GeoTIFF files found in {input_dir}")
        return

    for src_fp in tif_paths:
        fname = os.path.basename(src_fp)
        dst_fp = os.path.join(output_dir, fname)
        if os.path.exists(dst_fp) and not overwrite:
            print(f"Skipping existing file {dst_fp}")
            continue

        # build warp options using cutlineWKT
        warp_kwargs = {
            'cutlineWKT': wkt_polygon,
            'cutlineSRS': f"EPSG:{src_srs_epsg}",
            'cropToCutline': crop_to_cutline,
            'dstNodata': None,
            'format': 'GTiff'
        }

        warp_opts = gdal.WarpOptions(**warp_kwargs)
        out_ds = gdal.Warp(dst_fp, src_fp, options=warp_opts)
        if out_ds:
            out_ds = None
            print(f"Written subset: {dst_fp}")
        else:
            print(f"ERROR: Failed to warp {src_fp}")


## Example usage:
"""
 python subset_geotiffs_by_wkt.py \
    /mnt/d/data_2/output/pituffik_20_21/geotiffs/ \
    /mnt/d/data_2/output/pituffik_20_21/geotiffs_subset_base/ \
    "POLYGON((-69.611 76.4068,-68.1443 76.4068,-68.1443 76.627,-69.611 76.627,-69.611 76.4068))"
"""

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python subset_geotiffs_by_wkt.py <input_dir> <output_dir> <wkt_polygon> [<src_epsg=4326>]")
        sys.exit(1)
    input_dir = sys.argv[1]
    output_dir = sys.argv[2]
    wkt = sys.argv[3]
    src_epsg = int(sys.argv[4]) if len(sys.argv) >= 5 else 4326
    subset_geotiff_by_wkt(input_dir, output_dir, wkt, src_srs_epsg=src_epsg)