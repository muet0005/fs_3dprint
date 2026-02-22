# fs_3dprint
# Code to convert FreeSurfer outputs into 3D-printable meshes. 

This code is heavily based on: https://github.com/miykael/3dprintyourbrain

The code is also heavily tailored for printing on BambuLab printers. 

What it will do:

1.) Convert the lh/rh surfaces into STL meshes

2.) Convert the non-cortical volume-based data into a single STL mesh

3.) Apply smoothing to the meshes, and also fix defects /issues with the meshes using pymeshlabs. 

4.) Merge all meshes together into a final STL file. 
