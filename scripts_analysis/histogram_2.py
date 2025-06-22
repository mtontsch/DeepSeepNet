#!/usr/bin/env python3
import os
import numpy as np
import rasterio
import matplotlib.pyplot as plt
from multiprocessing import Pool
from functools import partial
from matplotlib.lines import Line2D  # For custom legend handles
import argparse

from PIL import Image
Image.MAX_IMAGE_PIXELS = None  # Disable the limit entirely


def process_image_min_max(file_path):
    with rasterio.open(file_path) as dataset:
        data_channel1 = dataset.read(1)
        data_channel2 = dataset.read(2)
        # Flatten and remove NaNs
        data_channel1 = data_channel1.flatten()
        data_channel2 = data_channel2.flatten()
        data_channel1 = data_channel1[np.isfinite(data_channel1)]
        data_channel2 = data_channel2[np.isfinite(data_channel2)]
    min_val = min(data_channel1.min(), data_channel2.min())
    max_val = max(data_channel1.max(), data_channel2.max())
    return min_val, max_val


def compute_global_min_max(image_files, num_processes=1):
    with Pool(num_processes) as pool:
        min_max_list = pool.map(process_image_min_max, image_files)
    # Extract global min and max
    global_min = min([min_val for min_val, _ in min_max_list])
    global_max = max([max_val for _, max_val in min_max_list])
    return global_min, global_max


def process_image(file_path, bin_edges):
    with rasterio.open(file_path) as dataset:
        # Read both channels separately
        data_channel1 = dataset.read(1).flatten()
        data_channel2 = dataset.read(2).flatten()

        # Exclude NaN values
        data_channel1 = data_channel1[np.isfinite(data_channel1)]
        data_channel2 = data_channel2[np.isfinite(data_channel2)]

        # Compute histograms for each channel
        hist1, _ = np.histogram(data_channel1, bins=bin_edges)
        hist2, _ = np.histogram(data_channel2, bins=bin_edges)

    return hist1, hist2


def parallel_histogram(image_files, bin_edges, num_processes=1):
    with Pool(num_processes) as pool:
        func = partial(process_image, bin_edges=bin_edges)
        hist_list = pool.map(func, image_files)

    # Separate histograms for each channel and sum them
    hist1_list, hist2_list = zip(*hist_list)
    total_hist1 = np.sum(hist1_list, axis=0)
    total_hist2 = np.sum(hist2_list, axis=0)
    return total_hist1, total_hist2


def get_bin_edges(data_min, data_max, decimal_places=None, num_bins=None):
    """
    Generate bin edges for the histogram.
    """
    if num_bins is not None:
        bins = np.linspace(data_min, data_max, num_bins + 1)
    elif decimal_places is not None:
        bin_width = 10 ** (-decimal_places)
        bins = np.arange(data_min, data_max + bin_width, bin_width)
    else:
        raise ValueError("Either decimal_places or num_bins must be specified.")
    return bins


def determine_decimal_places(bin_width):
    """
    Determine the number of decimal places based on bin width.
    """
    if bin_width == 0:
        return 0
    decimal_places = 0
    while bin_width < 1:
        bin_width *= 10
        decimal_places += 1
    return decimal_places


def main(directories, num_processes, limit, decimal_places, num_bins):
    # These constants set the x-axis limits and maximum frequency for each channel.
    # Adjust as needed.
    HH_min, HH_max = -50, -5
    HV_min, HV_max = -50, -5
    HH_max_freq, HV_max_freq = 1.3e6, 0.6e7

    # Percentile levels, colors and sigma labels
    percentiles = [0.135, 2.275, 15.865, 84.135, 97.725, 99.865]
    colors = ['red', 'orange', 'green']  # for ±3σ, ±2σ, ±1σ respectively
    sigma_levels = ['±3σ', '±2σ', '±1σ']

    # Process each directory and store results
    results = []
    for directory in directories:
        image_files = [
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if f.lower().endswith(('.tif', '.tiff'))
        ]
        num_files = len(image_files)
        if limit is not None:
            image_files = image_files[:limit]
            print(f"In directory {directory}, processing the first {limit} files out of {num_files}.")
        else:
            print(f"In directory {directory}, processing all {num_files} files.")

        # Compute data range and bin edges for this directory
        data_min, data_max = compute_global_min_max(image_files, num_processes)
        print(f"Directory {directory} - data_min: {data_min}, data_max: {data_max}")

        bin_edges = get_bin_edges(data_min, data_max, decimal_places, num_bins)
        if num_bins is not None:
            bin_width = bin_edges[1] - bin_edges[0]
            # Optionally adjust the number of decimal places based on the computed bin width.
            decimal_places = determine_decimal_places(bin_width)
            print(f"Using num_bins={num_bins} resulting in bin_width={bin_width} and decimal_places={decimal_places}")
        else:
            print(f"Using decimal_places={decimal_places}")

        # Compute the histograms for HH and HV channels
        total_hist1, total_hist2 = parallel_histogram(image_files, bin_edges, num_processes)
        results.append({
            'directory': directory,
            'bin_edges': bin_edges,
            'hist_HH': total_hist1,
            'hist_HV': total_hist2,
            'decimal_places': decimal_places,
        })

    # Create a single figure with a grid layout:
    # one row per directory and two columns (left: HH, right: HV)
    n_rows = len(results)
    fig, axs = plt.subplots(n_rows, 2, figsize=(15, 3 * n_rows +1))
    # Ensure axs is always 2D (e.g. if n_rows == 1)
    if n_rows == 1:
        axs = np.array([axs])

    # Loop over the directories and plot the histograms
    for i, res in enumerate(results):
        bin_edges = res['bin_edges']
        # Compute bin centers from bin edges
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        dec_places = res['decimal_places']
        hist_HH = res['hist_HH']
        hist_HV = res['hist_HV']
        # Use the directory name (last part of the path) in the titles
        dir_basename = os.path.basename(os.path.normpath(res['directory']))

        # Loop over channels: j=0 for HH (left), j=1 for HV (right)
        for j, (hist, channel) in enumerate(zip([hist_HH, hist_HV], ['HH', 'HV'])):
            ax = axs[i, j]
            # Compute the cumulative distribution function (CDF)
            cdf = np.cumsum(hist)
            cdf = cdf / cdf[-1] * 100  # Convert to percentage

            # Plot the histogram as a bar chart
            ax.bar(
                bin_centers,
                hist,
                width=bin_edges[1] - bin_edges[0],
                align='center',
                color='grey',
                edgecolor='black',
                linewidth=0.5
            )

            # Compute the pixel values at the desired percentile positions
            percentile_values = []
            for perc in percentiles:
                idx = np.searchsorted(cdf, perc)
                if idx < len(bin_centers):
                    percentile_values.append(bin_centers[idx])
                else:
                    percentile_values.append(bin_centers[-1])

            # Plot vertical dashed lines at the computed percentile positions
            for k in range(3):
                ax.axvline(percentile_values[k], color=colors[k], linestyle='--', linewidth=1.5)
                ax.axvline(percentile_values[5 - k], color=colors[k], linestyle='--', linewidth=1.5)

            # Set x and y limits (using your fixed limits)
            if channel == 'HH':
                ax.set_xlim(HH_min, HH_max)
                ax.set_ylim(0, HH_max_freq)
            else:
                ax.set_xlim(HV_min, HV_max)
                ax.set_ylim(0, HV_max_freq)

            # Set the title and labels. The title contains the directory name and channel.
            if dir_basename == 'snap':
                title = 'SNAP'
            elif dir_basename == 'dima':
                title = 's1r (Murashkin et al.)'
            elif dir_basename == 'anton':
                title = 's1d (Korosov et al.)'
            else:
                title = 'Unknown'    
            ax.set_title(f"{title} - {channel}")


            ax.set_ylabel('Frequency')
            # For the bottom row, label the x-axis on the HV (right-side) subplot.
            if i == n_rows - 1:
                ax.set_xlabel(r'Pixel Value ($\sigma^0$ in dB)')

            # Add a secondary x-axis on top with percentile tick marks.
            ax_top = ax.twiny()
            ax_top.set_xlim(ax.get_xlim())
            # Show only percentile values that fall within the x-axis limits.
            perc_vals_within = [val for val in percentile_values if ax.get_xlim()[0] <= val <= ax.get_xlim()[1]]
            ax_top.set_xticks(perc_vals_within)
            perc_labels = [f"{val:.{dec_places}f}" for val in perc_vals_within]
            ax_top.set_xticklabels(perc_labels, color='black', rotation=45)
            ax_top.spines['top'].set_visible(False)
            ax_top.xaxis.set_ticks_position('top')
            ax_top.xaxis.set_label_position('top')

            # Add a legend for the percentile lines.
            if i == 0 and j == 1:
                custom_lines = [Line2D([0], [0], color=colors[k], linestyle='--', linewidth=1.5) for k in range(3)]
                custom_labels = [
                    f'{sigma_levels[0]} ({percentiles[0]}% - {percentiles[5]}%)',
                    f'{sigma_levels[1]} ({percentiles[1]}% - {percentiles[4]}%)',
                    f'{sigma_levels[2]} ({percentiles[2]}% - {percentiles[3]}%)'
                ]
                ax.legend(custom_lines, custom_labels, loc='upper right', title='Percentile limits around mean')
            ax.ticklabel_format(style='sci', axis='y', scilimits=(0, 0))
            ax.yaxis.set_offset_position('right')

    plt.suptitle('Pixel Value Distributions for 24 Pipeline-Processed Sentinel-1 Scenes', fontsize=16)
    plt.subplots_adjust(left=0.055, bottom=0.1, right=0.988, top=0.857, wspace=0.102, hspace=0.683)

    # Save the combined figure.
    # output_dir = '/mnt/d/data/pipeline_compare/'
    # combined_filename = os.path.join(output_dir, 'histogram_combined.png')
    # plt.savefig(combined_filename, dpi=300, bbox_inches='tight')
    plt.show()


# Example Usage
# python figures/histogram_2.py /mnt/d/data/pipeline_compare/geotiffs_by_pipeline/snap/ /mnt/d/data/pipeline_compare/geotiffs_by_pipeline/dima/ /mnt/d/data/pipeline_compare/geotiffs_by_pipeline/anton/
# python figures/histogram_2.py /mnt/raid01/SAR/Sentinel-1/Arctic/ArcticDeepSeepsData/pipeline_compare/geotiffs_by_pipeline/snap/ //mnt/raid01/SAR/Sentinel-1/Arctic/ArcticDeepSeepsData/pipeline_compare/geotiffs_by_pipeline/dima/ /mnt/raid01/SAR/Sentinel-1/Arctic/ArcticDeepSeepsData/pipeline_compare/geotiffs_by_pipeline/anton/



if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Generate histograms from GeoTIFF images in multiple directories.'
    )
    parser.add_argument(
        'directories',
        type=str,
        nargs='+',
        help='Paths to the directories containing GeoTIFF images.'
    )
    parser.add_argument(
        '--num_processes',
        type=int,
        default=4,
        help='Number of parallel processes to use. Default is 4.'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit the number of files to process per directory. Default processes all files.'
    )
    parser.add_argument(
        '--decimal_places',
        type=int,
        default=1,
        help='Number of decimal places for the histogram bin width.'
    )
    parser.add_argument(
        '--num_bins',
        type=int,
        default=254,
        help='Number of bins for the histogram.'
    )
    args = parser.parse_args()

    main(
        directories=args.directories,
        num_processes=args.num_processes,
        limit=args.limit,
        decimal_places=args.decimal_places,
        num_bins=args.num_bins
    )
