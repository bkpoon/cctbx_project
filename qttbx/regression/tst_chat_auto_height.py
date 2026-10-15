"""auto_height.set_auto_height(): a QTextEdit-family widget grows with
its content instead of scrolling. Both scrollbars are disabled and
the widget's height tracks document().size().height() + frame chrome.
Spec: ConversationView is the sole scroller; per-bubble scrollbars
stack visually badly."""

import os

from libtbx.utils import format_cpu_times


def _qapp():
  from qttbx.qt import QtWidgets
  from qttbx.widgets.font_init import init_default_app_font
  app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
  init_default_app_font(app)
  return app


def exercise_helper_disables_both_scrollbars():
  os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
  _qapp()
  from qttbx.qt import QtCore, QtWidgets
  from qttbx.widgets.chat.auto_height import set_auto_height
  w = QtWidgets.QPlainTextEdit()
  set_auto_height(w)
  assert w.verticalScrollBarPolicy() == QtCore.Qt.ScrollBarAlwaysOff
  assert w.horizontalScrollBarPolicy() == QtCore.Qt.ScrollBarAlwaysOff


def exercise_height_grows_with_content():
  """A widget configured by set_auto_height(): setPlainText with more
  content must produce a larger fixed height than less content AND
  the height must actually fit the rendered text (rough check: at
  least ~N - 2 lines for an N-line plain-text document).

  Regression: QPlainTextDocumentLayout reports documentSize().height()
  as the BLOCK count, not pixels -- the long_h > short_h check passed
  even when long_h was off by ~16x (84 px for 80 lines that need
  ~1280 px). The 'fits the content' assertion below catches that.

  The widget must be shown so its viewport has a real width --
  without it block layout treats the document as zero-width."""
  os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
  app = _qapp()
  from qttbx.qt import QtWidgets
  from qttbx.widgets.chat.auto_height import set_auto_height
  w = QtWidgets.QPlainTextEdit()
  w.resize(400, 800)
  w.show()
  set_auto_height(w)
  w.setPlainText("one short line")
  app.processEvents()
  short_h = w.height()
  n_lines = 80
  many = "\n".join("line %d" % i for i in range(n_lines))
  w.setPlainText(many)
  app.processEvents()
  long_h = w.height()
  assert long_h > short_h, (short_h, long_h)
  line_h = w.fontMetrics().lineSpacing()
  needed = (n_lines - 2) * line_h
  assert long_h >= needed, (long_h, needed, line_h, n_lines)
  # And fits it whole: a view a few pixels short of its text -- the
  # top document margin was left out -- kept a one-line scroll range,
  # and a wheel notch, PageDown or Space over it shifted the text up a
  # line instead of scrolling the conversation.
  _assert_nothing_to_scroll(w)


def _assert_nothing_to_scroll(w):
  ranges = (w.verticalScrollBar().maximum(), w.horizontalScrollBar().maximum())
  assert ranges == (0, 0), (
    "%d lines / %d px left for the widget's own scrollbars" % ranges)


def exercise_viewport_and_scroll_range_follow_a_rewrap():
  """A height set from the resize hook reaches the viewport.

  QAbstractScrollArea delivers resizeEvent for its viewport's resize,
  from inside its own child layout (guarded against re-entry) or, on
  first show, before the viewport is visible. Either way the widget
  grew and the viewport did not follow: an argument preview that
  rewrapped from three lines to five at a narrower window showed the
  first three, with the rest behind a scroll range of two for a wheel
  notch to reveal; a card shown at its minimum width kept the whole
  preview but one line. Widened back, the widget shrinks and the
  viewport has to follow it down as well.
  """
  os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
  app = _qapp()
  from qttbx.qt import QtWidgets
  from qttbx.widgets.chat.auto_height import set_auto_height

  def host_with(view):
    host = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(host)
    layout.addWidget(view)
    layout.addStretch(1)
    return host

  def settled(host, view):
    last = None
    for _ in range(50):
      app.processEvents()
      now = (view.height(), view.viewport().height())
      if now == last:
        break
      last = now
    assert view.viewport().height() == view.height() - 2 * view.frameWidth(), (
      "the viewport is %d px tall in a %d px widget"
      % (view.viewport().height(), view.height()))
    _assert_nothing_to_scroll(view)
    cursor = view.textCursor()
    cursor.movePosition(cursor.End)
    assert view.cursorRect(cursor).bottom() <= view.viewport().height(), (
      "the last line is clipped")

  # First show at a width the text needs several lines at.
  view = QtWidgets.QPlainTextEdit()
  view.setPlainText("ACGT" * 60)
  set_auto_height(view)
  host = host_with(view)
  host.resize(250, 600)
  host.show()
  settled(host, view)
  three_lines = view.height()
  # Then the squeeze: the text rewraps and the widget grows in the hook.
  host.resize(140, 600)
  settled(host, view)
  assert view.height() > three_lines, (view.height(), three_lines)
  # And back: fewer lines, a shorter widget, the viewport with it.
  host.resize(250, 600)
  settled(host, view)
  assert view.height() == three_lines, (view.height(), three_lines)
  host.close()


def exercise():
  exercise_helper_disables_both_scrollbars()
  exercise_height_grows_with_content()
  exercise_viewport_and_scroll_range_follow_a_rewrap()


if __name__ == "__main__":
  exercise()
  print(format_cpu_times())
  print("OK")
