from omacad.ui.smart_circle import ACROSS, DOWN, SIZE, SmartCircle, nearest_axis_line

WALLS = [((0, 0), (0, 50), "left"), ((60, 0), (60, 50), "right"), ((0, 0), (60, 0), "bottom"),
         ((0, 50), (60, 50), "top"), ((0, 0), (30, 30), "diag")]


def _sc():
    s = SmartCircle()
    s.segments = WALLS
    return s


def _type(s, text):
    s.text = text


def test_nearest_vertical_and_horizontal_ignore_slanted_lines():
    assert nearest_axis_line(WALLS, (50, 10), True)[2] == "right"
    assert nearest_axis_line(WALLS, (5, 10), True)[2] == "left"
    assert nearest_axis_line(WALLS, (20, 45), False)[2] == "top"
    assert nearest_axis_line([((0, 0), (30, 30), "d")], (1, 1), True) is None


def test_full_flow_with_numbers_only():
    s = _sc()
    s.mouse = (50, 10)
    assert s.accept() == "need_size"
    _type(s, "8")
    assert s.accept() == "next" and s.stage == ACROSS and s.diameter == 8
    s.mouse = (48, 20)                       # right wall is nearest, mouse on its left
    _type(s, "10")
    assert s.centre() == (50, 20)            # 10 in from x=60
    assert s.accept() == "next" and s.stage == DOWN
    s.mouse = (15, 44)                       # top wall, mouse below it
    _type(s, "6")
    assert s.centre() == (50, 44)
    assert s.accept() == "done"
    assert s.dimension[ACROSS][0][2] == "right" and s.dimension[ACROSS][1] == 10
    assert s.dimension[DOWN][0][2] == "top"
    assert s.centre() == (50, 44)


def test_empty_step_takes_the_mouse_and_makes_no_dimension():
    s = _sc()
    s.mouse = (30, 25)
    _type(s, "5"); s.accept()
    s.mouse = (22, 25); assert s.accept() == "next"
    s.mouse = (22, 31); assert s.accept() == "done"
    assert s.centre() == (22, 31) and not s.dimension


def test_negative_distance_flips_side_and_backspace_goes_back():
    s = _sc()
    s.mouse = (5, 25)
    _type(s, "4"); s.accept()
    _type(s, "-3")
    assert s.centre()[0] == -3               # mouse is right of x=0, minus puts it on the other side
    s.text = ""
    assert s.back() and s.stage == SIZE


def test_typed_distance_without_a_line_is_refused():
    s = SmartCircle()
    s.mouse = (1, 1)
    _type(s, "4"); s.accept()
    _type(s, "2")
    assert s.accept() == "no_line"
