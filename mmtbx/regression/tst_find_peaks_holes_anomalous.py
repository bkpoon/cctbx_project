"""Anomalous-map branch of mmtbx.find_peaks_holes on synthetic Bijvoet data"""
from __future__ import absolute_import, division, print_function
from libtbx.utils import null_out
from six.moves import cStringIO as StringIO
import libtbx.load_env
import iotbx.pdb
import os

def make_inputs(file_base="tst_find_peaks_holes_anom"):
  """
  Synthetic anomalous data from a calcium-binding fragment, plus the same
  model with the calcium deleted so the anomalous map has one unmodelled
  scatterer to find.

  Returns
  -------
  tuple of str, str, tuple of float
      PDB file (no calcium), MTZ file (F(+)/F(-)), calcium site (cartesian).
  """
  from mmtbx.regression.make_fake_anomalous_data import generate_calcium_inputs
  mtz_file, pdb_file = generate_calcium_inputs(
    file_base=file_base, anonymize=False)
  pdb_in = iotbx.pdb.input(pdb_file)
  hierarchy = pdb_in.construct_hierarchy()
  sel = hierarchy.atom_selection_cache().selection("element CA")
  assert sel.count(True) == 1
  ca_site = hierarchy.atoms().select(sel)[0].xyz
  pdb_no_ca = file_base + "_no_ca.pdb"
  hierarchy.select(~sel).write_pdb_file(
    file_name=pdb_no_ca,
    crystal_symmetry=pdb_in.crystal_symmetry())
  assert os.path.isfile(pdb_no_ca)
  return pdb_no_ca, mtz_file, ca_site

def check_result(result, log, ca_site, crystal_symmetry):
  """The strongest anomalous peak sits on the deleted calcium."""
  assert "Anomalous difference map peaks" in log, log
  assert result.anom_peaks is not None
  n_peaks = len(result.anom_peaks.heights)
  assert n_peaks > 0, log
  uc = crystal_symmetry.unit_cell()
  ca_frac = uc.fractionalize(ca_site)
  # container pre-sorts by height, descending
  top = result.anom_peaks.sites[0]
  # nearest lattice image
  diff = [a - b for a, b in zip(uc.fractionalize(top), ca_frac)]
  diff = [d - round(d) for d in diff]
  dist = uc.length(diff)
  assert dist < 1.0, (dist, top, ca_site)

def exercise_cli(pdb_file, mtz_file, ca_site):
  """Command-line entry: Phaser LLG map when phaser is configured."""
  from mmtbx.command_line import find_peaks_holes
  out = StringIO()
  result = find_peaks_holes.run(
    args=[pdb_file, mtz_file, "write_pdb=False", "write_maps=False"],
    out=out)
  log = out.getvalue()
  if libtbx.env.has_module("phaser"):
    assert "Will use Phaser LLG map" in log, log
  crystal_symmetry = iotbx.pdb.input(pdb_file).crystal_symmetry()
  check_result(result, log, ca_site, crystal_symmetry)

def exercise_cli_no_phaser(pdb_file, mtz_file, ca_site):
  """Command-line entry with the LLG map switched off: anom_residual map."""
  from mmtbx.command_line import find_peaks_holes
  out = StringIO()
  result = find_peaks_holes.run(
    args=[pdb_file, mtz_file, "write_pdb=False", "write_maps=False",
          "use_phaser_if_available=False"],
    out=out)
  log = out.getvalue()
  assert "Will use Phaser LLG map" not in log, log
  crystal_symmetry = iotbx.pdb.input(pdb_file).crystal_symmetry()
  check_result(result, log, ca_site, crystal_symmetry)

def exercise_library(pdb_file, mtz_file, ca_site):
  """Library entry with the LLG map switched off: anom_residual map."""
  import mmtbx.command_line
  from mmtbx.command_line import find_peaks_holes
  cmdline = mmtbx.command_line.load_model_and_data(
    args=[pdb_file, mtz_file],
    master_phil=find_peaks_holes.master_phil,
    out=null_out(),
    process_pdb_file=False,
    create_fmodel=True,
    prefer_anomalous=True)
  assert cmdline.fmodel.f_obs().anomalous_flag()
  out = StringIO()
  result = find_peaks_holes.find_peaks_holes(
    fmodel=cmdline.fmodel,
    pdb_hierarchy=cmdline.pdb_hierarchy,
    params=cmdline.params.find_peaks,
    use_phaser_if_available=False,
    out=out)
  log = out.getvalue()
  assert "Will use Phaser LLG map" not in log, log
  check_result(result, log, ca_site,
               cmdline.fmodel.xray_structure.crystal_symmetry())

def run():
  pdb_file, mtz_file, ca_site = make_inputs()
  exercise_library(pdb_file, mtz_file, ca_site)
  exercise_cli(pdb_file, mtz_file, ca_site)
  exercise_cli_no_phaser(pdb_file, mtz_file, ca_site)
  print("OK")

if (__name__ == "__main__"):
  run()
