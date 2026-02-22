#!/usr/bin/env python3

"""
Author: Ryan Muetzel
Email: 
Created 16 Feb 2025
License:
Version 0.9.0

Usage:
    python3

Description:
    Code to convert freesurfer surface meshes to 3D printable meshes. 
    Relies heavily on:
    https://github.com/miykael/3dprintyourbrain
    Relies heavily on:
    bambulabs printing setup.

"""

import os
import sys
import subprocess as sp
import argparse
import logging
from pathlib import Path
import shutil
import nibabel as nb
import numpy as np
import gzip
import pymeshlab as pml 

# check that freesurfer is installed...
def check_env(varname):
    """
    Make sure a required environment variable is set
    Args:
        environment var name
    Raises:
        EnvironmentError: If the environment variable is not set.
    """
    value = Path(os.environ.get(varname))
    if value is None:
        raise EnvironmentError(f"Environment variable {varname} is not set.")
    return value
fs_home = check_env("FREESURFER_HOME")
if not fs_home.exists():
    raise NotADirectoryError(f"Environment variable {varname} is not a real path.")

def check_program_exists(program):
    """
    Make sure freesurfer tools are in PATH environment variable
    Args:
        example fs cmd
    Raises:
        KeyError: if not in path.
    """
    if shutil.which(program) is None:
        raise KeyError(f"ERROR: '{program}' not found in PATH.")
check_program_exists("mri_convert")

# Start up logger
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

# start up parser for passed args
parser = argparse.ArgumentParser(description="Create 3D surface meshses of freesurfer output suitable for 3D printing")
parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
parser.add_argument("-c", "--clobber", action="store_true", help="Overwrite existing outputs")
parser.add_argument("-sd", "--subjectsDir", type=Path, help="FreeSurfer SUBJECTS_DIR", required = True)
parser.add_argument("-s", "--subjid", help="Particpant ID (as stored in SUBJECTS_DIR)", required = True)
parser.add_argument("-md", "--meshDir", type=Path, help="Output folder to store mesh files", required = True)
args = parser.parse_args()

# set logger to debug if requested
if args.verbose:
    logging.getLogger().setLevel(logging.DEBUG)

overWrite = False
if args.clobber:
    overWrite: bool = args.clobber

# get required arguments
subjects_dir: Path = args.subjectsDir
subjid: str = args.subjid
meshDir: Path = args.meshDir

logging.info(f"SUBJECTS_DIR: {subjects_dir}")
logging.info(f"Subject ID:    {subjid}")
logging.info(f"Mesh Output:   {meshDir}")

def cvt_fsSurf_to_stl(lh_pial: Path, rh_pial: Path, oDir: Path):
    """
    Convert a FreeSurfer surface to an STL file type using mri_convert
    
    Parameters
    ----------
    
    lh_pial : Path 
        Path to left hemi pial surface
    rh_pial Path
        Path to right hemi pial surface
    oDir : Path
        Path to where to store the outputs
    
    Raises
    ------
    FileNotFoundError
        If the subject folder or required surface files are missing.
    """
    if not lh_pial.exists():
        raise FileNotFoundError(f"Missing LH surface: {lh_pial}")
    if not rh_pial.exists():
        raise FileNotFoundError(f"Missing RH surface: {rh_pial}")
    if not oDir.exists():
        try:
            oDir.mkdir(parents=True, exist_ok=False)
        except Exception as e:
            raise OSError(f"Failed to create output directory {oDir}: {e}")
    oFile = oDir.joinpath('bh.cortical.stl')
    if oFile.exists() and not overWrite:
        logging.info(f"output file exists...overWrite disables...skipping: {oFile}")
        return oFile
    cmd = [
        "mris_convert",
        "--combinesurfs",
        str(lh_pial),
        str(rh_pial),
        str(oFile)
    ]
    logging.info(f"Running: {' '.join(cmd)}")

    result = sp.run(cmd, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
    if result.returncode != 0:
        logging.error(result.stderr)
        raise RuntimeError(f"mris_convert failed: {result.stderr}")
    return oFile
    
def cvt_aseg_to_stl(subj: str, subjects_dir: Path, oDir: Path):
    """
    Convert a FreeSurfer aseg vol to an STL file type using mri_convert & tesselate
    
    Parameters
    ----------
    
    subj : str
        subject ID
    subjects_dir Path
        Path SUBJECTS_DIR
    oDir : Path
        Path to where to store the outputs
    
    Raises
    ------
    FileNotFoundError
        If the subject folder or required surface files are missing.
    """
    # Point to ASEG segmentation volume
    aseg = Path(subjects_dir, subj, 'mri', 'aseg.mgz')
    if not aseg.exists():
        raise FileNotFoundError(f"Missing aseg.mgz: {aseg}")
    # load in
    subcortVol = Path(oDir, 'subcortical.nii.gz')
    if not subcortVol.exists() or overWrite:
        img = nb.load(str(aseg))
        data = img.get_fdata()
        # set the ROI index values
        MATCH_LABELS = [2, 3, 24, 31, 41, 42, 63, 72, 77, 51, 52, 13, 12, 43, 50, 4, 11, 26, 58, 49, 10, 17, 18, 53, 54, 44, 5, 80, 14, 15, 30, 62]
        # Mask the volume based on the ROI indices
        logging.info(f"Running: initial masking of aseg")
        mask = np.isin(data, MATCH_LABELS).astype(np.uint8)
        inv_mask = 1 - mask
        maskedData = data * inv_mask
        # save out the masked /binarized i mage
        out_img = nb.Nifti1Image(maskedData.astype(np.float32), img.affine, img.header)
        nb.save(out_img, str(subcortVol))
    else:
        logging.info(f"Running: initial masking of aseg already complete...skipping (use clobber to overwrite)")
    # I'm not sure why we make this tmp image
    tmpFile = Path(str(subcortVol).replace('.nii.gz', '_tmp.nii.gz'))
    if not tmpFile.exists() or overWrite:
        shutil.copy2(subcortVol, tmpFile)
    else:
        logging.info(f"Running: tmp file already created...skipping (use clobber to overwrite)")
    # run the pre-tess procedure on the ROIs we care about
    pretessInput = tmpFile.with_suffix('')
    if not pretessInput.exists() or overWrite:
        with gzip.open(tmpFile, 'rb') as f_in, open(pretessInput, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
        MATCH_LABELS = [7, 8, 16, 28, 46, 47, 60, 251, 252, 253, 254, 255]
        for i in MATCH_LABELS:
            cmd = [
                "mri_pretess",
                str(pretessInput),
                str(i),
                str(Path(subjects_dir, subj, "mri", "norm.mgz")),
                str(pretessInput)]
            logging.info(f"Running: {' '.join(cmd)}")
            result = sp.run(cmd, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
    else:
        logging.info(f"pre-tesselation already complete...skipping (use clobber to overwrite)")
    # Binarize the whole volume
    tessInput = Path(oDir, 'subcortical_bin.nii.gz')
    if not tessInput.exists() or overWrite:
        cmd = [
            'fslmaths',
            str(pretessInput),
            '-bin',
            str(tessInput)
            ]
        logging.info(f"Running: {' '.join(cmd)}")
        result = sp.run(cmd, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
    else:
        logging.info(f"binarization of pretess already complete...skipping (use clobber to overwrite)")
    # now run the final tesselation
    tessOut = Path(oDir, 'subcortical')
    if not tessOut.exists() or overWrite:
        cmd = [
            'mri_tessellate',
            str(tessInput), 
            str(1),
            str(tessOut)
            ]
        logging.info(f"Running: {' '.join(cmd)}")
        result = sp.run(cmd, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
    else:
        logging.info(f"tesselation already complete...skipping (use clobber to overwrite)")
    subcortStl = Path(oDir, 'subcortical.stl')
    if not subcortStl.exists() or overWrite:
        cmd = [
            'mris_convert',
            str(tessOut),
            str(subcortStl)
            ]
        logging.info(f"Running: {' '.join(cmd)}")
        result = sp.run(cmd, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
    else:
        logging.info(f"STL File exists...skipping (use clobber to overwrite)")
    return subcortStl

def create_printable_mesh(cortexMesh: Path, subcortMesh: Path, oDir: Path, useSepSmoothed: bool = False, stepsmoothnumCort: int = 100, stepsmoothnumsubCort: int = 8, resamplePrecision: float = 0.275, resampleOffsetPerc: float = 52.5, rmConCompSize: int = 10000, lapSmoothSteps: int = 3):
    """
    """
    smoothedCortex = Path(oDir, 'bh.cortex.smoothed.stl')
    smoothedSubcort = Path(oDir, 'bh.subcort.smoothed.stl')
    if not smoothedCortex.exists() or overWrite:
        logging.info(f"Running smoothing of cortical and subcortical surfaces")
        cortex = pml.MeshSet()
        cortex.load_new_mesh(str(cortexMesh))
        subcort = pml.MeshSet()
        subcort.load_new_mesh(str(subcortMesh))
        cortex.apply_coord_laplacian_smoothing_scale_dependent(stepsmoothnum = stepsmoothnumCort)
        subcort.apply_coord_laplacian_smoothing_scale_dependent(stepsmoothnum = stepsmoothnumsubCort)
        cortex.save_current_mesh(str(smoothedCortex), binary=True)
        subcort.save_current_mesh(str(smoothedSubcort), binary=True)
        logging.info(f"created: {smoothedCortex}")
        logging.info(f"created: {smoothedSubcort}")
    else:
        logging.info(f"Skipping smoothing of cortical and subcortical surfaces....use --clobber to overwrite")

    wholeBrainMesh = Path(oDir.parent, 'bh.wholebrain.smoothed.stl')
    if not wholeBrainMesh.exists() or overWrite:
        logging.info(f"Running merging of cortical and subcortical surfaces")
        wb_mesh = pml.MeshSet()
        if useSepSmoothed:
            wb_mesh.load_new_mesh(str(smoothedCortex))
            wb_mesh.load_new_mesh(str(smoothedSubcort))
        else:
            wb_mesh.load_new_mesh(str(cortexMesh))
            wb_mesh.load_new_mesh(str(subcortMesh))
        wb_mesh.generate_by_merging_visible_meshes()
        logging.info(f"repairing non-manifold edges")
        wb_mesh.meshing_repair_non_manifold_edges()
        logging.info(f"repairing non-manifold vertices")
        wb_mesh.meshing_repair_non_manifold_vertices()
        logging.info(f"resampling mesh")
        wb_mesh.generate_resampled_uniform_mesh(cellsize = pml.Percentage(resamplePrecision), offset = pml.Percentage(resampleOffsetPerc))
        logging.info(f"removing connected comp.")
        wb_mesh.meshing_remove_connected_component_by_face_number(mincomponentsize = rmConCompSize)
        logging.info(f"final smoothing")
        wb_mesh.apply_coord_laplacian_smoothing(stepsmoothnum = lapSmoothSteps)
        logging.info(f"saving final mesh...mesh {wholeBrainMesh}")
        wb_mesh.save_current_mesh(str(wholeBrainMesh), binary=True)
    else:
        logging.info(f"Skipping merging of cortical and subcortical surfaces....use --clobber to overwrite")



lh_pial = Path(subjects_dir, subjid, 'surf', 'lh.pial')
rh_pial = Path(subjects_dir, subjid, 'surf', 'rh.pial')
oDir = Path(meshDir, subjid, 'preprocessing')
cortexMesh = cvt_fsSurf_to_stl(lh_pial=lh_pial, rh_pial=rh_pial, oDir=oDir)
subcortMesh = cvt_aseg_to_stl(subj=subjid, subjects_dir=subjects_dir, oDir=oDir)
create_printable_mesh(cortexMesh, subcortMesh, oDir)
