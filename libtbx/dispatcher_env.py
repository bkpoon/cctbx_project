"""Environment hygiene shared by every dispatcher writer.

A dispatcher runs in a copy of the caller's environment. Several variables in
that environment make Python or the dynamic loader pick up code from outside
the installation: PYTHONPATH and PYTHONHOME, the per-user site-packages
directory, LD_PRELOAD and the DYLD_* search and insert variables, the module
paths of GTK, GIO, GDK-pixbuf, fontconfig and Qt that a desktop session or
another conda environment exports, and matplotlib's backend and rc
overrides. The guard emitted here clears them and disables user
site-packages before the interpreter starts. Setting either name in
``dispatcher_environment_opt_outs`` skips the guard, for callers who
deliberately combine environments.

This module must stay importable with only the standard library: the
development-build include generator runs before libtbx is configured.
"""
from __future__ import absolute_import, division, print_function

dispatcher_environment_opt_outs = (
  "CCTBX_CONDA_USE_ENVIRONMENT_VARIABLES",
  "PHENIX_TRUST_OTHER_ENV",
)

# Cleared by the POSIX guard.
dispatcher_cleared_variables = (
  # Python
  "PYTHONHOME", "PYTHONPATH",
  # dynamic loader
  "LD_LIBRARY_PATH", "LD_PRELOAD",
  "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH",
  "DYLD_FRAMEWORK_PATH", "DYLD_FALLBACK_FRAMEWORK_PATH",
  "DYLD_INSERT_LIBRARIES",
  # GTK, GIO, GDK-pixbuf, fontconfig (wxPython on Linux, bundled Coot)
  "GTK_MODULES", "GTK_PATH", "GTK_IM_MODULE", "GTK_IM_MODULE_FILE",
  "GTK2_RC_FILES",
  "GDK_PIXBUF_MODULE_FILE", "GDK_PIXBUF_MODULEDIR",
  "GIO_MODULE_DIR", "GIO_EXTRA_MODULES",
  "FONTCONFIG_FILE", "FONTCONFIG_PATH",
  # Qt
  "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QPA_PLATFORMTHEME",
  "QT_STYLE_OVERRIDE",
  # matplotlib
  "MPLBACKEND", "MATPLOTLIBRC",
)

# Cleared by the Windows guard. DLLs resolve through PATH there, which the
# dispatcher already puts the installation first on.
dispatcher_cleared_variables_win32 = (
  "PYTHONHOME", "PYTHONPATH",
  "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QPA_PLATFORMTHEME",
  "QT_STYLE_OVERRIDE",
  "MPLBACKEND", "MATPLOTLIBRC",
)

# Set by the guard.
dispatcher_set_variables = (
  ("PYTHONNOUSERSITE", "1"),
)
dispatcher_set_variables_win32 = (
  ("PYTHONNOUSERSITE", "1"),
  # conda's Python then resolves extension-module DLLs from the installation
  # instead of searching PATH
  ("CONDA_DLL_SEARCH_MODIFICATION_ENABLE", "1"),
)

_comment = (
  "Isolate this run from the caller's environment: PYTHONPATH, user",
  "site-packages, preloaded libraries and GUI-toolkit module paths from",
  "another Python or desktop session would otherwise shadow the packages",
  "shipped here. To keep the caller's environment instead, set",
  "%s or %s." % dispatcher_environment_opt_outs,
)


def environment_guard_lines(shell, inside=()):
  """Lines that clear the caller's environment before Python starts.

  Parameters
  ----------
  shell : str
      "sh" or "bat".
  inside : sequence of str
      Extra lines placed inside the guarded block, so they are skipped too
      when a caller opts out.
  """
  if shell == "sh":
    lines = ["# " + c for c in _comment]
    lines.append("if %s; then" % " && ".join(
      '[ -z "${%s}" ]' % v for v in dispatcher_environment_opt_outs))
    for v in dispatcher_cleared_variables:
      lines.append("  unset %s" % v)
    for name, value in dispatcher_set_variables:
      lines.append("  %s=%s" % (name, value))
      lines.append("  export %s" % name)
    for line in inside:
      lines.append("  " + line)
    lines.append("fi")
    return lines
  if shell == "bat":
    lines = ["@rem " + c for c in _comment]
    lines.append("@" + " ".join(
      "if not defined %s" % v for v in dispatcher_environment_opt_outs) + " (")
    for v in dispatcher_cleared_variables_win32:
      lines.append('  @set "%s="' % v)
    for name, value in dispatcher_set_variables_win32:
      lines.append('  @set "%s=%s"' % (name, value))
    for line in inside:
      lines.append("  " + line)
    lines.append(")")
    return lines
  raise ValueError("shell must be 'sh' or 'bat', not %r" % (shell,))


def external_path_lines(shell):
  """Opt-in search paths for the DivCon (QuantumBio) integration, appended
  after the guard so they are kept whether or not the caller's environment is
  trusted. Only the POSIX dispatchers carry them."""
  if shell == "bat":
    return []
  if shell != "sh":
    raise ValueError("shell must be 'sh' or 'bat', not %r" % (shell,))
  lines = [
    "# Opt-in paths for the DivCon (QuantumBio) integration; appended after",
    "# the guard so they are kept either way.",
  ]
  for var in ("PYTHONPATH", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
    qb = "QB_" + var
    lines += [
      'if [ -n "${%s}" ]; then' % qb,
      '  %s="${%s:+${%s}:}${%s}"' % (var, var, var, qb),
      '  export %s' % var,
      'fi',
    ]
  return lines
