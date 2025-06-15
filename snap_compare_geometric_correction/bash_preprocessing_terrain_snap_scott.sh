#!/bin/bash

# --- Configuration ---

# Check for correct number of arguments
if [ "$#" -ne 1 ]; then
    echo "Error! Usage: $0 <path_to_textfile_with_scene_zip_names>"
    exit 1
fi

# Path to txt file with scene names (e.g., scenename_1.zip)
inputFileList_path="$1"

# Path to root directory with raw zip files
root_dir="/mnt/raid01/SAR/Sentinel-1/Arctic/ScottTrough/raw_root/"

# Path to directory for output tifs (base directory)
# Output files will be saved like: output_dir/scene_name/scene_name_graphname.tif
# output_dir_base="/mnt/raid01/SAR/Sentinel-1/Arctic/WesternSvalbard/pipeline_snap/"
output_dir_base="/mnt/raid01/SAR/Sentinel-1/Arctic/ArcticDeepSeepsData/geometric_correction/scott/"

# --- List of SNAP XML graph files to process sequentially ---
# Define the graphs you want to run here
graphXml_files=(
    "xml/ScottTrough/ORB_BN_TN_CAL_SPCK_ECGG_Subset_Inc.xml"
    "xml/ScottTrough/ORB_BN_TN_CAL_SPCK_ECRD_Subset_Inc.xml"
    "xml/ScottTrough/ORB_BN_TN_CAL_SPCK_TC_Subset_Inc.xml"
)

# Path to the SNAP gpt executable
gpt_executable="/home/mtontsch/esasnap/bin/gpt"

# Path to the post-processing Python script
python_script="convert_to_NaN_and_dB.py"

# --- Helper Function ---

# Helper function to get the full path to the scene folder via scene name and data root directory
getScenePath() {
    local zip_file_name="$1"
    local source_root="$2"
    echo "$(python3 -c "import sys, os; from sentinel1_routines.scene_management import get_scene_folder; \
        zip_file_name = sys.argv[1]; \
        source_root = sys.argv[2]; \
        print(get_scene_folder(zip_file_name, source_root))" \
        "$zip_file_name" "$source_root")"
}
# --- Main Processing Logic ---


    

# Start time of the script and counter for the scenes
start_time=$(date +%s)
scene_count=1
total_scenes=$(wc -l < "$inputFileList_path")

echo "Starting processing..."
echo "Input scene list: $inputFileList_path"
echo "Raw data root: $root_dir"
echo "Output base directory: $output_dir_base"
echo "Number of scenes to process: $total_scenes"
echo "Number of graphs per scene: ${#graphXml_files[@]}"
echo "Graphs to be applied:"
for graph in "${graphXml_files[@]}"; do
    echo "  - $graph"
done
echo "--------------------------------------------------------------------"


# Read each line/scene from the text file
while IFS= read -r zip_file_name || [[ -n "$zip_file_name" ]]; do
    # Skip empty lines
    [ -z "$zip_file_name" ] && continue

    # Use the Python helper to get the full path to the scene directory
    scene_dir=$(getScenePath "$zip_file_name" "$root_dir")
    if [ $? -ne 0 ]; then
        echo "Error: Could not get path for $zip_file_name. Skipping."
        echo "--------------------------------------------------------------------"
        continue # Skip to the next scene
    fi

    # Check if scene directory ends with a slash, add if not (robustness)
    [[ "$scene_dir" != */ ]] && scene_dir="${scene_dir}/"

    zip_file="${scene_dir}${zip_file_name}"
    scene_name="${zip_file_name%.zip}"

    echo ""
    echo "Processing scene #$scene_count of $total_scenes: $scene_name"
    echo "Source Zip File: $zip_file"

    # Check if the source zip file exists
    if [ ! -f "$zip_file" ]; then
        echo "Error: Source file not found: $zip_file. Skipping scene."
        echo "--------------------------------------------------------------------"
        scene_count=$((scene_count + 1))
        continue
    fi

    # Create a subdirectory for this scene's output
    output_scene_dir="$output_dir_base/$scene_name"
    mkdir -p "$output_scene_dir"
    if [ $? -ne 0 ]; then
        echo "Error: Could not create output directory: $output_scene_dir. Skipping scene."
        echo "--------------------------------------------------------------------"
        scene_count=$((scene_count + 1))
        continue
    fi
    echo "Output directory for this scene: $output_scene_dir"


    # --- Inner loop: Iterate through the list of XML graph files ---
    graph_count=1
    total_graphs=${#graphXml_files[@]}
    for graphXml_file in "${graphXml_files[@]}"; do
        echo ""
        echo "  Applying graph #$graph_count of $total_graphs: $graphXml_file"

        # Check if the graph file exists
        if [ ! -f "$graphXml_file" ]; then
            echo "  Error: Graph XML file not found: $graphXml_file. Skipping this graph."
            graph_count=$((graph_count + 1))
            continue # Skip to the next graph
        fi

        graphXml_name=$(basename "$graphXml_file" | cut -d. -f1)

        # Define the final output file path for this specific scene and graph
        outputFileSnap_name="${scene_name}_${graphXml_name}.tif"
        outputFileSnap_path="$output_scene_dir/$outputFileSnap_name"

        echo "    Output target: $outputFileSnap_path"

        # Check if the final output file already exists, skip if desired (optional)
        # if [ -f "$outputFileSnap_path" ]; then
        #    echo "    Output file already exists. Skipping SNAP processing for this graph."
        #    graph_count=$((graph_count + 1))
        #    continue
        # fi

        ## APPLY SNAP GRAPH PROCESSING ###
        echo -e "    Running SNAP graph processing..."
        "$gpt_executable" "$graphXml_file" -Psource="$zip_file" -Ptarget="$outputFileSnap_path"

        # Check if SNAP GPT processing was successful
        if [ $? -ne 0 ]; then
            echo "    Error: SNAP gpt command failed for graph $graphXml_file on scene $scene_name."
            echo "    Skipping subsequent steps for this graph."
            graph_count=$((graph_count + 1))
            # Optional: remove partially created/failed output file
            # rm -f "$outputFileSnap_path"
            continue # Skip to the next graph
        fi
        echo "    SNAP processing completed."

        ## Convert to NaN Values and dB (if the python script exists) ##
        if [ -f "$python_script" ]; then
            echo "    Running Python script ($python_script) on output..."
            python "$python_script" "$outputFileSnap_path"

            # Check if Python script execution was successful
            if [ $? -ne 0 ]; then
                echo "    Error: Python script $python_script failed for $outputFileSnap_path."
                # Decide if you want to keep the GPT output or remove it
                # rm -f "$outputFileSnap_path"
            else
                echo "    Python script completed."
            fi
        else
            echo "    Warning: Python script $python_script not found. Skipping this step."
        fi
        
        # No renaming needed now as the graph name is included in the target path

        echo "  Finished processing graph $graphXml_name for scene $scene_name."
        graph_count=$((graph_count + 1))

    done # --- End of inner loop for graphs ---

    echo ""
    echo "Done processing all graphs for scene $scene_name"
    scene_count=$((scene_count + 1))
    echo "--------------------------------------------------------------------"
    echo "--------------------------------------------------------------------"

done < "$inputFileList_path"

# --- Finalization ---

# End time of the script
end_time=$(date +%s)

# Calculate total runtime in seconds
total_runtime=$((end_time - start_time))

# Convert total runtime to hours, minutes, and seconds
hours=$((total_runtime / 3600))
minutes=$(( (total_runtime % 3600) / 60))
seconds=$((total_runtime % 60))

# Print the total runtime
actual_processed_count=$((scene_count - 1))
echo ""
echo "Finished processing $actual_processed_count scenes!"
printf "Total runtime: %02d:%02d:%02d (H:M:S)\n" $hours $minutes $seconds
echo "Output files are located in subdirectories within: $output_dir_base"

