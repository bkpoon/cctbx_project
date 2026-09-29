"""Verify the environment guard the dispatchers emit before running Python.

The guard clears the variables through which a caller's environment can
inject code or libraries into the shipped Python: PYTHONPATH and PYTHONHOME,
the loader search and preload variables, GUI-toolkit module paths (GTK, GIO,
GDK-pixbuf, fontconfig, Qt) and matplotlib's backend and rc overrides. It also
disables the per-user site-packages directory (PYTHONNOUSERSITE). Setting
either CCTBX_CONDA_USE_ENVIRONMENT_VARIABLES or PHENIX_TRUST_OTHER_ENV opts
out of the whole guard.

The DivCon integration variables (QB_PYTHONPATH, QB_LD_LIBRARY_PATH,
QB_DYLD_LIBRARY_PATH) are appended after the guard so they survive it.
"""

import os
import shutil
import subprocess
import tempfile

import libtbx.load_env
from libtbx import env_config
from libtbx.utils import format_cpu_times

IS_NT = (os.name == "nt")

PROBE = ["PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE", "LD_LIBRARY_PATH",
         "LD_PRELOAD", "GTK_MODULES", "QT_PLUGIN_PATH", "MPLBACKEND",
         "CONDA_DLL_SEARCH_MODIFICATION_ENABLE", "CCTBX_TST_INSIDE"]

POLLUTION = {
  "PYTHONPATH": "/pp",
  "PYTHONHOME": "/ph",
  "LD_LIBRARY_PATH": "/ll",
  "LD_PRELOAD": "/usr/lib/libinjected.so",
  "GTK_MODULES": "canberra-gtk-module",
  "QT_PLUGIN_PATH": "/usr/lib/qt/plugins",
  "MPLBACKEND": "QtAgg",
}


def write_file(path, text):
  with open(path, "w") as f:
    f.write(text)


def parse_output(text):
  result = {}
  for line in text.splitlines():
    if "=" in line:
      key, _, value = line.partition("=")
      result[key.strip()] = value.strip()
  return result


def make_harness(tmp, shell):
  inside = (['@set "CCTBX_TST_INSIDE=1"'] if shell == "bat"
            else ["CCTBX_TST_INSIDE=1", "export CCTBX_TST_INSIDE"])
  body = (env_config.environment_guard_lines(shell, inside=inside)
          + env_config.external_path_lines(shell))
  if shell == "bat":
    header = ["@echo off", 'set "LIBTBX_PREFIX=%s"' % tmp]
    footer = ["if defined %s (echo %s=%%%s%%) else (echo %s=UNSET)"
              % (v, v, v, v) for v in PROBE]
    script = os.path.join(tmp, "harness.bat")
  else:
    header = ["#!/bin/sh", 'LIBTBX_PREFIX="%s"' % tmp, "export LIBTBX_PREFIX"]
    footer = ['echo "%s=${%s:-UNSET}"' % (v, v) for v in PROBE]
    script = os.path.join(tmp, "harness.sh")
  write_file(script, "\n".join(header + body + footer) + "\n")
  if shell != "bat":
    os.chmod(script, 0o755)
  return script


def run_harness(script, extra_env):
  child_env = os.environ.copy()
  for v in PROBE + list(env_config.dispatcher_environment_opt_outs) \
      + ["QB_PYTHONPATH", "QB_LD_LIBRARY_PATH", "QB_DYLD_LIBRARY_PATH"]:
    child_env.pop(v, None)
  child_env.update(POLLUTION)
  child_env.update(extra_env)
  cmd = ["cmd", "/c", script] if IS_NT else [script]
  p = subprocess.run(cmd, env=child_env, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, universal_newlines=True)
  assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
  return parse_output(p.stdout)


def exercise_guard_runtime():
  """Run the guard in a shell and check what the child process sees."""
  shell = "bat" if IS_NT else "sh"
  tmp = os.path.realpath(tempfile.mkdtemp())
  try:
    script = make_harness(tmp, shell)

    # Default: everything polluting is gone, user site is off, the lines
    # placed inside the guard ran.
    out = run_harness(script, {})
    for v in POLLUTION:
      assert out[v] == "UNSET", (v, out)
    assert out["PYTHONNOUSERSITE"] == "1", out
    assert out["CCTBX_TST_INSIDE"] == "1", out
    if IS_NT:
      assert out["CONDA_DLL_SEARCH_MODIFICATION_ENABLE"] == "1", out

    # Either opt-out name disables the guard entirely.
    for opt_out in env_config.dispatcher_environment_opt_outs:
      out = run_harness(script, {opt_out: "1"})
      for v, value in POLLUTION.items():
        assert out[v] == value, (opt_out, v, out)
      assert out["PYTHONNOUSERSITE"] == "UNSET", (opt_out, out)
      assert out["CCTBX_TST_INSIDE"] == "UNSET", (opt_out, out)

    if not IS_NT:
      # DivCon paths are appended after the guard, without a leading
      # separator when the guard emptied the variable.
      out = run_harness(script, {"QB_PYTHONPATH": "/qb",
                                 "QB_LD_LIBRARY_PATH": "/qbl"})
      assert out["PYTHONPATH"] == "/qb", out
      assert out["LD_LIBRARY_PATH"] == "/qbl", out
      out = run_harness(script, {"QB_PYTHONPATH": "/qb",
                                 "PHENIX_TRUST_OTHER_ENV": "1"})
      assert out["PYTHONPATH"] == "/pp" + os.pathsep + "/qb", out
  finally:
    shutil.rmtree(tmp, ignore_errors=True)


def exercise_generated_dispatchers():
  """The conda-package dispatcher and the development-build include both
  carry the guard, ahead of the conda activation block."""
  env = libtbx.env
  env._dispatcher_include_at_start = []
  env._dispatcher_include_before_command = []
  env._dispatcher_precall_commands = []
  tmp = os.path.realpath(tempfile.mkdtemp())
  try:
    bin_dir = os.path.join(tmp, "bin")
    os.makedirs(bin_dir)
    source_file = os.path.join(tmp, "tst_guard_src.py")
    write_file(source_file, "print('hello')\n")
    target_file = os.path.join(bin_dir, "tst_guard_disp")
    if IS_NT:
      target_file += ".bat"
    env.write_conda_dispatcher(
      source_file=env.as_relocatable_path(source_file),
      target_file=env.as_relocatable_path(target_file))
    with open(target_file) as f:
      text = f.read()
    for opt_out in env_config.dispatcher_environment_opt_outs:
      assert opt_out in text, (opt_out, text)
    assert "PYTHONNOUSERSITE=1" in text, text
    assert text.index("PYTHONNOUSERSITE=1") < text.index("activate.d"), text
    if IS_NT:
      assert "CONDA_DLL_SEARCH_MODIFICATION_ENABLE=1" in text, text
    else:
      assert "unset LD_PRELOAD" in text, text
      assert "QB_PYTHONPATH" in text, text

    if not IS_NT:
      # development-build include (write_gui_dispatcher_include --use_conda)
      from libtbx.auto_build import write_gui_dispatcher_include
      build_dir = os.path.join(tmp, "build")
      base_dir = os.path.join(tmp, "base")
      os.makedirs(os.path.join(base_dir, "lib"))
      os.makedirs(build_dir)
      write_gui_dispatcher_include.run([
        "--build_dir=%s" % build_dir,
        "--base_dir=%s" % base_dir,
        "--suffix=tst",
        "--use_conda",
        "--ignore_missing_dirs",
        "--quiet",
      ])
      with open(os.path.join(build_dir, "dispatcher_include_tst.sh")) as f:
        text = f.read()
      for opt_out in env_config.dispatcher_environment_opt_outs:
        assert opt_out in text, (opt_out, text)
      assert "PYTHONNOUSERSITE=1" in text, text
      assert "unset LD_PRELOAD" in text, text
      assert "libtbx.scons" in text, text
      assert "QB_PYTHONPATH" in text, text
  finally:
    shutil.rmtree(tmp, ignore_errors=True)


def exercise():
  exercise_guard_runtime()
  exercise_generated_dispatchers()


if __name__ == "__main__":
  exercise()
  print(format_cpu_times())
  print("OK")
