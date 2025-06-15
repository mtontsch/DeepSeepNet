#!/usr/bin/env python3

import sys
import os
import numpy as np
from osgeo import gdal
# disable exceptions to handle errors gracefully
gdal.UseExceptions()




def convert_to_NaN_and_dB(input_file):
    # Generate output file name
    dirname, basename = os.path.split(input_file)
    name, ext = os.path.splitext(basename)
    output_file = os.path.join(dirname, f"{name}{ext}")

    # Open the input file
    ds = gdal.Open(input_file, gdal.GA_ReadOnly)
    if ds is None:
        print(f"Failed to open {input_file}")
        sys.exit(1)

    # Get geotransform, projection, and band count
    geotransform = ds.GetGeoTransform()
    projection = ds.GetProjection()
    band_count = ds.RasterCount

    # Get dimensions
    xsize = ds.RasterXSize
    ysize = ds.RasterYSize

    # Create the output dataset
    driver = gdal.GetDriverByName('GTiff')
    out_ds = driver.Create(
        output_file,
        xsize,
        ysize,
        band_count,
        gdal.GDT_Float32
    )

    if out_ds is None:
        print(f"Failed to create {output_file}")
        sys.exit(1)

    # Set geotransform and projection
    out_ds.SetGeoTransform(geotransform)
    out_ds.SetProjection(projection)

    # Process each band
    for band_number in range(1, band_count + 1):
        # Read data from input band
        band = ds.GetRasterBand(band_number)
        data = band.ReadAsArray().astype(np.float32)

        # Replace zero values with NaN
        data[data == 0] = np.nan

        # Convert to dB for bands other than the third band (incidence angle)
        if band_number != 3:
            # Suppress warnings for log of zero or negative numbers
            with np.errstate(divide='ignore', invalid='ignore'):
                data = 10 * np.log10(data)

        # Write data to output band
        out_band = out_ds.GetRasterBand(band_number)
        out_band.WriteArray(data)
        out_band.FlushCache()

        # Optionally set NoData value
        out_band.SetNoDataValue(np.nan)

        print(f"Processed band {band_number}")

    # Close datasets
    ds = None
    out_ds = None

    print(f"Converted file saved as {output_file}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python convert_to_NaN_and_dB.py <input_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    convert_to_NaN_and_dB(input_file)
