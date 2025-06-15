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

# Path to root directory with raw zip files
dir_root="/mnt/d/data_2/raw_root_scott_2025/"

# Path to directory for output tifs
dir_output="/mnt/d/data_2/output_wide/"

# Path to snap xml graph
# file_graph="/home/mtontsch/DeepSeepNetRepo/preprocessing_pipelines/xml/ORB_BN_TN_CAL_SPCK_TC_Subset.xml"
file_graph="/home/mtontsch/DeepSeepNetRepo/preprocessing_pipelines/xml/ORB_BN_TN_CAL_SPCK_TC_Subset_LSMask.xml"
name_graph=$(basename "$file_graph" | cut -d. -f1)

# file_landmask="/mnt/f/ArcticDeepSeepsData/shapefiles/shapefiles_regional/osm_scott_buffered/ScottTrough_5px.shp"
file_landmask="/mnt/f/ArcticDeepSeepsData/temp/land_polygons_buffered_40m_5px_wide/land_polygons_buffered_40m_5px.shp"
name_landmask=$(basename "$file_landmask" | cut -d. -f1)



wkt_polyon="POLYGON((-71.395 71.032, -68.645 71.032, -68.645 71.912, -71.395 71.912, -71.395 71.032))"



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
        -PutmZone="19" \
        -Plandmask_path="$file_landmask" \
        -Plandmask_name="$name_landmask" \

    echo ""
    # Convert to NaN Values and dB ##
    python convert_to_NaN_and_dB.py "$path_outputFileSnap"
    echo ""


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
