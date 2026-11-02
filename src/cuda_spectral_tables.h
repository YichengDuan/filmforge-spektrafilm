// GPL-3.0-only. Profile data layout shared by CPU preparation and CUDA.
#pragma once
struct SpectralTables {
  int wavelengths, film_exposures, paper_exposures, hanatos_width, hanatos_height;
  const float *film_log_e, *film_curves, *film_dyes, *film_min;
  const float *paper_log_e, *paper_curves, *paper_dyes;
  const float *response, *print_weights, *scan_weights;
  float input_xyz[9], gray_xyz[9], output_rgb[9], scan_normalization;
  float *print_scale;
};
// Prepared by the unchanged upstream CPU helpers; no Vulkan calls are made.
struct SpatialParams {
  float floats[105];
  unsigned ints[29];
  unsigned diffusion_count;
  float diffusion_scatter;
  float diffusion_components[32 * 4];
};
extern "C" {
void* ff_spectral_tables_create(int film,int paper,const char* resource_dir);
const SpectralTables* ff_spectral_tables_view(void* owner);
void ff_spectral_tables_destroy(void* owner);
const char* ff_spectral_tables_error();
int ff_spectral_stock_count(int paper);
const char* ff_spectral_stock(int paper,int index);
int ff_spectral_spatial_params(int film,int width,int height,float grain,float halation,float diffusion,
                              unsigned seed,unsigned frame,SpatialParams* output);
}
