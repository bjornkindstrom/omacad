import numpy as np
from omacad.ui.viewport.render_mixin import dash_lines


def _px(p):
    return (float(p[0]), float(p[1]))


def test_straight_line_is_cut_into_dashes():
    out = np.array(dash_lines([0, 0, 0, 150, 0, 0], _px)).reshape(-1, 2, 3)
    assert len(out) == 10                       # 150 px / (9+6)
    assert np.allclose(out[0], [[0, 0, 0], [9, 0, 0]])
    assert np.allclose(out[1][0], [15, 0, 0])


def test_phase_carries_over_short_segments():
    flat = []
    for i in range(30):                         # 30 pieces of 5 px = same line as 150 px
        flat += [i * 5, 0, 0, i * 5 + 5, 0, 0]
    out = np.array(dash_lines(flat, _px)).reshape(-1, 2, 3)
    total = sum(np.linalg.norm(b - a) for a, b in out)
    assert abs(total - 90.0) < 1e-6             # 10 dashes of 9 px
