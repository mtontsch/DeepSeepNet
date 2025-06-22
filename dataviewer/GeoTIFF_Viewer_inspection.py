import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider
from osgeo import gdal
import cmocean

gdal.UseExceptions()
gdal.PushErrorHandler('CPLQuietErrorHandler')


class GeoTIFFViewer:
    def __init__(self, directory):
        # Load and sort GeoTIFF files
        self.directory = directory
        self.file_list = sorted(
            [f for f in os.listdir(directory) if f.lower().endswith(('.tif', '.tiff'))],
            key=lambda x: (x[17:25], x[26:32])
        )
        
        # Figure with two subplots
        self.fig, self.ax = plt.subplots(1, 2, figsize=(16, 7))

        # Slider for navigation
        self.slider_ax = plt.axes([0.2, 0.9, 0.65, 0.03])
        self.slider = Slider(self.slider_ax, 'Image Index', 0,
                             len(self.file_list) - 1, valinit=0, valstep=1)

        # Initial display limits
        self.vmin_HH, self.vmax_HH = -40, 0
        self.vmin_HV, self.vmax_HV = -50, -20
        self.sigma_level = 4
        self.display_mode = 'both'  # 'both', 'HH', or 'HV'

        # Events
        self.slider.on_changed(self.update)
        self.fig.canvas.mpl_connect('key_press_event', self.on_key)

        # Initial draw
        self.update(0)
        print("Funcs: [1-4]=σ clipping, [c]=save name, [←/→]=navigate, [h/v/b]=layout")


    def on_key(self, event):
        if event.key in ['right', 'left']:
            step = 1 if event.key == 'right' else -1
            self.current_file_index = (self.current_file_index + step) % len(self.file_list)
            self.slider.set_val(self.current_file_index)
            return

        if event.key == 'c':
            self.save_current_scenename()
            return

        if event.key in ['1', '2', '3', '4']:
            self.sigma_level = int(event.key)
            self.toggle_limits()
            self.update_display()
            print(f'Sigma level set to {self.sigma_level}')
            return

        if event.key in ['h', 'v', 'b']:
            # Set display mode
            self.display_mode = {'h': 'HH', 'v': 'HV', 'b': 'both'}[event.key]
            # Reload current data for new mode
            self.load_geotiff(self.current_file_index)
            self.toggle_limits()
            self.update_display()
            print(f'Display mode: {self.display_mode}')
            return

    def save_current_scenename(self):
        print(f"Copied product ID {self.current_scenename} to textfile.")
        out_file = '/mnt/c/Users/Maximilian Tontsch/Nextcloud/PolarRS/workspace_thesis/txt/big_oil.txt'
        with open(out_file, 'a') as f:
            f.write(self.current_scenename + '\n')

    def toggle_limits(self):
        # Apply percentile or manual limits only for loaded channels
        if self.sigma_level in [1, 2, 3]:
            upper = [84.135, 97.725, 99.865]
            lower = [15.865, 2.275, 0.135]
            if self.display_mode in ['both', 'HH'] and self.subset_1 is not None:
                arr = self.subset_1[~np.isnan(self.subset_1)]
                self.vmin_HH = np.percentile(arr, lower[self.sigma_level - 1])
                self.vmax_HH = np.percentile(arr, upper[self.sigma_level - 1])
            if self.display_mode in ['both', 'HV'] and self.subset_2 is not None:
                arr = self.subset_2[~np.isnan(self.subset_2)]
                self.vmin_HV = np.percentile(arr, lower[self.sigma_level - 1])
                self.vmax_HV = np.percentile(arr, upper[self.sigma_level - 1])
        else:
            # manual fixed limits
            self.vmin_HH, self.vmax_HH = -38.4, -1.4
            self.vmin_HV, self.vmax_HV = -47.6, -16.7

    def load_geotiff(self, idx):
        # Load only necessary bands based on display_mode
        name = self.file_list[idx]
        self.current_scenename = name.replace('.tif', '').replace('.tiff', '')
        path = os.path.join(self.directory, name)
        ds = gdal.Open(path)

        # Only load required raster bands
        self.subset_1 = ds.GetRasterBand(1).ReadAsArray().astype(float) if self.display_mode in ['both', 'HH'] else None
        self.subset_2 = ds.GetRasterBand(2).ReadAsArray().astype(float) if self.display_mode in ['both', 'HV'] else None

        # Optional third band
        if ds.RasterCount > 2:
            self.subset_3 = ds.GetRasterBand(3).ReadAsArray().astype(float)
            self.mean_inc_angle = np.nanmean(self.subset_3)

    def update(self, val):
        self.current_file_index = int(val)
        self.load_geotiff(self.current_file_index)
        self.toggle_limits()
        self.update_display()
        # Print current file info
        print('-' * 120)
        print(f"Loaded: {self.file_list[self.current_file_index]}")
        if self.subset_1 is not None:
            print(f"Image size : {self.subset_1.shape}")
        if self.subset_2 is not None:
            print(f"Image size : {self.subset_2.shape}")

        

    def update_display(self):
        # Clear axes
        for a in self.ax:
            a.cla()

        # Determine subplot positions
        sp = self.fig.subplotpars
        fw = sp.right - sp.left
        fh = sp.top - sp.bottom
        ws = sp.wspace
        half = (fw - ws) / 2

        positions = {
            'left': [sp.left, sp.bottom, half, fh],
            'right': [sp.left + half + ws, sp.bottom, half, fh],
            'full': [sp.left, sp.bottom, fw, fh]
        }

        # Set visibility & positions
        self.ax[0].set_visible(self.display_mode != 'HV')
        self.ax[1].set_visible(self.display_mode != 'HH')

        if self.display_mode == 'both':
            self.ax[0].set_position(positions['left'])
            self.ax[1].set_position(positions['right'])
        elif self.display_mode == 'HH':
            self.ax[0].set_position(positions['full'])
        else:
            self.ax[1].set_position(positions['full'])

        cmap = 'grey'

        # Plot HH if loaded
        if self.subset_1 is not None:
            im1 = self.ax[0].imshow(
                self.subset_1, cmap=cmap, vmin=self.vmin_HH, vmax=self.vmax_HH
            )
            self._format_axis(self.ax[0], im1, 'HH')

        # Plot HV if loaded
        if self.subset_2 is not None:
            # Always plot HV on ax1
            ax_hv = self.ax[1]
            im2 = ax_hv.imshow(
                self.subset_2, cmap=cmap, vmin=self.vmin_HV, vmax=self.vmax_HV
            )
            self._format_axis(ax_hv, im2, 'HV')

        # Super title
        date, time, sat = self.get_date_and_sat_from_filename(
            self.file_list[self.current_file_index]
        )
        st = f"{sat} | {date} | {time}"
        if self.display_mode == 'HH':
            st += " | HH"
        elif self.display_mode == 'HV':
            st += " | HV"
        else:
            st += " | HH & HV"
        if hasattr(self, 'mean_inc_angle'):
            st += r" | Mean $\theta_{inc}$.:" 
            st += f"{self.mean_inc_angle:.2f}"
            
        self.fig.suptitle(st, fontsize=16)
        plt.draw()

    def _format_axis(self, ax, im, label):
        ax.set_xticks([])
        ax.set_yticks([])
        cbar = self.fig.colorbar(
            im, ax=ax, orientation='horizontal',
            cax=ax.inset_axes([0.1, -0.1, 0.8, 0.05])
        )
        cbar.set_label(r'\sigma^0 [dB]')
        ax.set_title(f'{label} {self._title_suffix()}')

    def _title_suffix(self):
        labels = {1: '1σ', 2: '2σ', 3: '3σ', 4: 'manual'}
        return f"({labels[self.sigma_level]}) [{self.vmin_HH:.1f},{self.vmax_HH:.1f}]"

    def get_date_and_sat_from_filename(self, fn):
        dp, tp, sp = fn[17:25], fn[26:32], fn[:3]
        date = f"{dp[6:8]}.{dp[4:6]}.{dp[:4]}"
        time = f"{tp[0:2]}:{tp[2:4]}:{tp[4:6]}"
        sats = {'S1A': 'Sentinel-1A', 'S1B': 'Sentinel-1B', 'S1C': 'Sentinel-1C'}
        return date, time, sats.get(sp, 'Unknown')


if __name__ == '__main__':
    dir_path = '/mnt/d/data_2/output/pituffik_20_21/geotiffs_padded_subset_base/'
    # dir_path = '/mnt/d/data_2/output/pituffik_20_21/geotiffs/'

    viewer = GeoTIFFViewer(dir_path)
    plt.subplots_adjust(
        top=1.0, bottom=0.019, left=0.015, right=0.985,
        hspace=0.2, wspace=0.031
    )
    plt.show()
    print("Finished")
