#!/usr/bin/env python
# vim:fileencoding=utf-8
# License: GPL v3 Copyright: 2016, Kovid Goyal <kovid at kovidgoyal.net>

import math
import os
import re
import shlex
import string
import subprocess
from contextlib import contextmanager
from functools import lru_cache
from time import monotonic

from .constants import isosx, iswayland, selection_clipboard_funcs
from .fast_data_types import (
    GLSL_VERSION, glfw_get_physical_dpi, redirect_std_streams,
    wcwidth as wcwidth_impl
)
from .rgb import Color, to_color

BASE = os.path.dirname(os.path.abspath(__file__))


def load_shaders(name):
    vert = open(os.path.join(BASE, '{}_vertex.glsl'.format(name))).read().replace('GLSL_VERSION', str(GLSL_VERSION), 1)
    frag = open(os.path.join(BASE, '{}_fragment.glsl'.format(name))).read().replace('GLSL_VERSION', str(GLSL_VERSION), 1)
    return vert, frag


def safe_print(*a, **k):
    try:
        print(*a, **k)
    except Exception:
        pass


def ceil_int(x):
    return int(math.ceil(x))


@lru_cache(maxsize=2**13)
def wcwidth(c: str) -> int:
    try:
        return wcwidth_impl(ord(c))
    except TypeError:
        return wcwidth_impl(ord(c[0]))


@lru_cache()
def pt_to_px(pts):
    dpix, dpiy = get_dpi()['logical']
    dpi = (dpix + dpiy) / 2
    return round(pts * dpi / 72)


@contextmanager
def timeit(name, do_timing=False):
    if do_timing:
        st = monotonic()
    yield
    if do_timing:
        safe_print('Time for {}: {}'.format(name, monotonic() - st))


def sanitize_title(x):
    return re.sub(r'\s+', ' ', re.sub(r'[\0-\x19]', '', x))


@lru_cache()
def load_libx11():
    import ctypes
    from ctypes.util import find_library
    libx11 = ctypes.CDLL(find_library('X11'))
    ans = []

    def cdef(name, restype, *argtypes):
        f = getattr(libx11, name)
        if restype is not None:
            f.restype = restype
        if argtypes:
            f.argtypes = argtypes
        ans.append(f)

    cdef('XOpenDisplay', ctypes.c_void_p, ctypes.c_char_p)
    cdef('XCloseDisplay', ctypes.c_int, ctypes.c_void_p)
    cdef('XResourceManagerString', ctypes.c_char_p, ctypes.c_void_p)
    return ans


def parse_xrdb(raw):
    q = 'Xft.dpi:\t'
    for line in raw.decode('utf-8').splitlines():
        if line.startswith(q):
            return float(line[len(q):])


def x11_dpi_native():
    XOpenDisplay, XCloseDisplay, XResourceManagerString = load_libx11()
    display = XOpenDisplay(None)
    if display is None:
        raise RuntimeError('Could not connect to the X server')
    try:
        raw = XResourceManagerString(display)
        return parse_xrdb(raw)
    finally:
        XCloseDisplay(display)


def x11_dpi():
    try:
        return x11_dpi_native()
    except Exception:
        pass
    try:
        raw = subprocess.check_output(['xrdb', '-query'])
        return parse_xrdb(raw)
    except Exception:
        pass


def get_logical_dpi():
    if not hasattr(get_logical_dpi, 'ans'):
        if isosx or iswayland:
            # TODO: Investigate if this needs a different implementation on OS X or Wayland
            get_logical_dpi.ans = glfw_get_physical_dpi()
        else:
            # See https://github.com/glfw/glfw/issues/1019 for why we cant use
            # glfw_get_physical_dpi()
            dpi = x11_dpi()
            if dpi is None:
                get_logical_dpi.ans = glfw_get_physical_dpi()
            else:
                get_logical_dpi.ans = dpi, dpi
    return get_logical_dpi.ans


def get_dpi():
    if not hasattr(get_dpi, 'ans'):
        pdpi = glfw_get_physical_dpi()
        get_dpi.ans = {'physical': pdpi, 'logical': get_logical_dpi()}
    return get_dpi.ans


def color_as_int(val):
    return val[0] << 16 | val[1] << 8 | val[2]


def color_from_int(val):
    return Color((val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)


def parse_color_set(raw):
    parts = raw.split(';')
    for c, spec in [parts[i:i + 2] for i in range(0, len(parts), 2)]:
        try:
            c = int(c)
            if c < 0 or c > 255:
                raise IndexError('Out of bounds')
            r, g, b = to_color(spec)
            yield c, r << 16 | g << 8 | b
        except Exception:
            continue


def set_primary_selection(text):
    if isosx:
        return  # There is no primary selection on OS X
    if isinstance(text, str):
        text = text.encode('utf-8')
    s = selection_clipboard_funcs()[1]
    if s is None:
        p = subprocess.Popen(['xsel', '-i', '-p'], stdin=subprocess.PIPE, stdout=open(os.devnull, 'wb'), stderr=subprocess.STDOUT)
        p.stdin.write(text), p.stdin.close()
        p.wait()
    else:
        s(text)


def get_primary_selection():
    if isosx:
        return ''  # There is no primary selection on OS X
    g = selection_clipboard_funcs()[0]
    if g is None:
        ans = subprocess.check_output(['xsel', '-p'], stderr=open(os.devnull, 'wb'), stdin=open(os.devnull, 'rb')).decode('utf-8')
        if ans:
            # Without this for some reason repeated pastes dont work
            set_primary_selection(ans)
    else:
        ans = (g() or b'').decode('utf-8', 'replace')
    return ans


def base64_encode(
    integer,
    chars=string.ascii_uppercase + string.ascii_lowercase + string.digits +
    '+/'
):
    ans = ''
    while True:
        integer, remainder = divmod(integer, 64)
        ans = chars[remainder] + ans
        if integer == 0:
            break
    return ans


def open_url(url, program='default'):
    if program == 'default':
        cmd = ['open'] if isosx else ['xdg-open']
    else:
        cmd = shlex.split(program)
    cmd.append(url)
    subprocess.Popen(cmd).wait()


def detach(fork=True, setsid=True, redirect=True):
    if fork:
        # Detach from the controlling process.
        if os.fork() != 0:
            raise SystemExit(0)
    if setsid:
        os.setsid()
    if redirect:
        redirect_std_streams(os.devnull)


def adjust_line_height(cell_height, val):
    if isinstance(val, int):
        return cell_height + val
    return int(cell_height * val)
