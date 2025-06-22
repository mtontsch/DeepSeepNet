#!/bin/bash

if [ "$#" -ne 1 ]; then
    echo "Error! Usage: $0 <path_to_textfile>"
    exit 1
fi


# Path to txt file with scene names
# scenename_1.zip
# scenename_2.zip
# ...
inputFileList_path="$1"

# Path to root directory with raw Sentinel-1 zip files: default arg 
dir_root="/mnt/d/data_2/raw_root/pituffik/"

# Path to directory for output tifs: default arg 
dir_output="/mnt/d/data_2/output/pituffik_20_21/"

# Path to the xml file for the SNAP graph processing tool (gpt): option with vs. without land-sea-mask
# file_graph="/home/mtontsch/DeepSeepNet/preprocessing_pipelines/xml/ORB_BN_TN_CAL_SPCK_TC_Subset_LSMask.xml"
file_graph="/home/mtontsch/DeepSeepNet/preprocessing_pipelines/xml/ORB_BN_TN_CAL_SPCK_TC_Subset.xml"

# Path to shapefile for SNAPS's land-sea-mask operator: use if necessary
file_landmask="/home/mtontsch/DeepSeepNet/data/shapefiles/osm_buffered_diskobay/osm_land_polygons_buffered_40m_8px.shp"

# Option: Set utm zone and define subset as WKT polygon
# Disko Bay:
# wkt_polyon="POLYGON((-54.014 68.5991,-51.194 68.5991,-51.194 69.4841,-54.014 69.4841,-54.014 68.5991))"
# Pituffik Space Base:
utm_zone="19"
central_meridian="-69.0" # for UTM zone 19
wkt_polyon="POLYGON(( \
                    -72.290654 76.868834,\
                    -66.439580 76.877091,\
                    -66.570601 76.155830,\
                    -72.122401 76.148019,\
                    -72.290654 76.868834\
                    ))"

# For S1_EW_GRDM_1SDH data products:
pixelSpacingInMeter="40.0"
pixelSpacingInDegree="3.593261136478086E-4" 
# For 

# For later use
name_graph=$(basename "$file_graph" | cut -d. -f1)
name_landmask=$(basename "$file_landmask" | cut -d. -f1)


# Start time of the script and counter for the scenes
start_time=$(date +%s)
count=1

# Read each line/scene from the text file
while IFS= read -r file_zip_name; do
    # Use the Python helper to get the full path to raw zip file

    file_zip="$dir_root$file_zip_name"
    name_scene="${file_zip_name%.zip}"
    echo ""
    echo "Reading file: $file_zip"
    echo "Processing scene #$count: $name_scene"

     ## APPLY CORRECTION ###
    # name_outputFileSnap="${name_scene}.tif"
    path_outputFileSnap="${dir_output}${name_scene}.tif"
    echo "Output file will be: $path_outputFileSnap"
    
    echo -e "Doing SNAP graph processing ... \n"
    /home/mtontsch/esa-snap/bin/gpt "$file_graph" \
        -Psource="$file_zip" \
        -Ptarget="$path_outputFileSnap" \
        -PgeoRegion="$wkt_polyon" \
        -PutmZone="$utm_zone" \
        -Pcentral_meridian="$central_meridian" \
        -PpixelSpacingInMeter="$pixelSpacingInMeter" \
        -PpixelSpacingInDegree="$pixelSpacingInDegree" \
        -Plandmask_path="$file_landmask" \
        -Plandmask_name="$name_landmask"

    echo ""
    # Convert to NaN Values and dB ##
    python convert_to_NaN_and_dB.py "$path_outputFileSnap"
    echo ""
    # check if following script is executed correctly, if not exit and print error message
    if [ $? -ne 0 ]; then
        echo "Error: convert_to_NaN_and_dB.py failed for $name_scene"
        exit 1
    fi


    echo "Done processing scene $name_scene"

    # rename output file by appending 'SNAP' to the filename
    # mv "$outputFileNaN_path" "${outputFileNaN_path%.tif}_RAW.tif" # raw*
    mv "$path_outputFileSnap" "${path_outputFileSnap%.tif}_SNAP.tif"

    count=$((count + 1))
    echo "--------------------------------------------------------------------"
    echo "--------------------------------------------------------------------"   


done < "$inputFileList_path"

# End time of the script
end_time=$(date +%s)

# Calculate total runtime in seconds
total_runtime=$((end_time - start_time))

# Convert total runtime to hours, minutes, and seconds
hours=$((total_runtime / 3600))
minutes=$(( (total_runtime % 3600) / 60))
seconds=$((total_runtime % 60))

# Print the total runtime
echo ""
echo "Finished processing all $((count - 1)) scenes!" 
