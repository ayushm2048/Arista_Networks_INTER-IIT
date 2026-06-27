import numpy as np

# Replace with your filename
file_path = 'embeddings_sugar_mywifi.npy'

# Load the file (allow_pickle is required for dictionaries)
data = np.load(file_path, allow_pickle=True)

# Extract the dictionary from the 0-dimensional array wrapper
if data.ndim == 0:
    data_dict = data.item()
    print("Keys found:", list(data_dict.keys()))
else:
    print("This file is a standard array and does not have keys.")

# Assuming data_dict was loaded in the step above
target_key = 'ACCESS_POINT_4'  # <--- Change this manually

# Access and print the content
content = data_dict[target_key]
print(f"Shape/Type of {target_key}:", type(content))
print(content.shape)
print(content)