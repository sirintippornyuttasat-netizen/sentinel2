import ee
import geemap

# Initialize the Earth Engine library.
try:
    ee.Initialize(project='project-183fe1c7-ddb0-4eea-8c2')
except Exception:
    print("Earth Engine not authenticated. Starting authentication flow...")
    ee.Authenticate()
    ee.Initialize(project='project-183fe1c7-ddb0-4eea-8c2')

def mask_s2_clouds(image):
    """Function to mask clouds using the Sentinel-2 QA band."""
    qa = image.select('QA60')

    # Bits 10 and 11 are clouds and cirrus, respectively.
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11

    # Both flags should be set to zero, indicating clear conditions.
    mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(
        qa.bitwiseAnd(cirrus_bit_mask).eq(0)
    )

    return image.updateMask(mask).divide(10000)

# Load Sentinel-2 L2A HARMONIZED imagery.
dataset = (
    ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterDate('2020-01-01', '2020-01-30')
    # Pre-filter to get less cloudy granules.
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
    .map(mask_s2_clouds)
)

# Visualization parameters
visualization = {
    'min': 0.0,
    'max': 0.3,
    'bands': ['B4', 'B3', 'B2'],
}

# Create a map object using geemap
Map = geemap.Map()

# Set center of the map
Map.setCenter(83.277, 17.7009, 12)

# Add the mean image to the map
Map.addLayer(dataset.mean(), visualization, 'RGB')

# Save the map to an HTML file as a fallback.
Map.to_html(filename="map.html")
print("Saved map to 'map.html'. You can double-click this file to view the interactive map.")
