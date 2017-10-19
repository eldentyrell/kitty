#!/usr/bin/env python
# vim:fileencoding=utf-8
# License: GPL v3 Copyright: 2016, Kovid Goyal <kovid at kovidgoyal.net>

import os
import pwd
import ctypes
import sys
from collections import namedtuple

from .fast_data_types import set_boss as set_c_boss

appname = 'kitty'
version = (0, 3, 0)
str_version = '.'.join(map(str, version))
_plat = sys.platform.lower()
isosx = 'darwin' in _plat


ScreenGeometry = namedtuple('ScreenGeometry', 'xstart ystart xnum ynum dx dy')
WindowGeometry = namedtuple('WindowGeometry', 'left top right bottom xnum ynum')


def _get_config_dir():
    # This must be called before calling setApplicationName
    if 'KITTY_CONFIG_DIRECTORY' in os.environ:
        return os.path.abspath(os.path.expanduser(os.environ['VISE_CONFIG_DIRECTORY']))

    candidate = os.path.abspath(os.path.expanduser(os.environ.get('XDG_CONFIG_HOME') or ('~/Library/Preferences' if isosx else '~/.config')))
    ans = os.path.join(candidate, appname)
    os.makedirs(ans, exist_ok=True)
    return ans


config_dir = _get_config_dir()
del _get_config_dir


class ViewportSize:

    __slots__ = ('width', 'height', 'x_ratio', 'y_ratio')

    def __init__(self):
        self.width = self.height = 1024
        self.x_ratio = self.y_ratio = 1.0

    def __repr__(self):
        return '(width={}, height={}, x_ratio={}, y_ratio={})'.format(self.width, self.height, self.x_ratio, self.y_ratio)


def get_boss():
    return get_boss.boss


def set_boss(m):
    get_boss.boss = m
    set_c_boss(m)


def wakeup():
    get_boss.boss.child_monitor.wakeup()


viewport_size = ViewportSize()
cell_size = ViewportSize()
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
terminfo_dir = os.path.join(base_dir, 'terminfo')
logo_data_file = os.path.join(base_dir, 'logo', 'kitty.rgba')
shell_path = pwd.getpwuid(os.geteuid()).pw_shell or '/bin/sh'

GLint = ctypes.c_int if ctypes.sizeof(ctypes.c_int) == 4 else ctypes.c_long
GLuint = ctypes.c_uint if ctypes.sizeof(ctypes.c_uint) == 4 else ctypes.c_ulong
GLfloat = ctypes.c_float
if ctypes.sizeof(GLfloat) != 4:
    raise RuntimeError('float size is not 4')
if ctypes.sizeof(GLint) != 4:
    raise RuntimeError('int size is not 4')


def get_glfw_lib_name():
    try:
        for line in open('/proc/{}/maps'.format(os.getpid())):
            lib = line.split()[-1]
            if '/libglfw.so' in lib:
                return lib
    except Exception as err:
        try:
            print(str(err), file=sys.stderr)
        except Exception:
            pass
    return 'libglfw.so.3'


def glfw_lib():
    ans = getattr(glfw_lib, 'ans', None)
    if ans is None:
        ans = glfw_lib.ans = ctypes.CDLL('libglfw.3.dylib' if isosx else get_glfw_lib_name())
    return ans


def selection_clipboard_funcs():
    ans = getattr(selection_clipboard_funcs, 'ans', None)
    if ans is None:
        lib = glfw_lib()
        if hasattr(lib, 'glfwGetX11SelectionString'):
            g = lib.glfwGetX11SelectionString
            g.restype = ctypes.c_char_p
            g.argtypes = []
            s = lib.glfwSetX11SelectionString
            s.restype = None
            s.argtypes = [ctypes.c_char_p]
            ans = g, s
        else:
            ans = None, None
        selection_clipboard_funcs.ans = ans
    return ans


iswayland = not isosx and hasattr(glfw_lib(), 'glfwGetWaylandDisplay')
