"""SVBONY SDK v1.13.4: used only inside the single camera worker thread.

Verified Pi SDK: /home/arn/svbony-sdk/SVBCameraSDK/lib/armv8/libSVBCameraSDK.so
"""
import ctypes as C
import os

WIDTH, HEIGHT = 3856, 2180
RAW_BYTES = WIDTH * HEIGHT * 2
GAIN, EXPOSURE, RAW16 = 0, 1, 4


class CameraInfo(C.Structure):
    _fields_ = [
        ("FriendlyName", C.c_char * 32),
        ("CameraSN", C.c_char * 32),
        ("PortType", C.c_char * 32),
        ("DeviceID", C.c_uint),
        ("CameraID", C.c_int),
    ]


class SDKError(RuntimeError):
    def __init__(self, operation, code):
        self.code = code
        super().__init__(f"{operation} returned SDK code {code}")


class SVBDriver:
    def __init__(self):
        self.lib = C.CDLL(os.getenv(
            "ASTROPI_SVB_SDK",
            "/home/arn/svbony-sdk/SVBCameraSDK/lib/armv8/libSVBCameraSDK.so",
        ))
        signatures = {
            "SVBGetNumOfConnectedCameras": [],
            "SVBGetCameraInfo": [C.POINTER(CameraInfo), C.c_int],
            "SVBOpenCamera": [C.c_int],
            "SVBCloseCamera": [C.c_int],
            "SVBSetROIFormat": [C.c_int] * 6,
            "SVBSetOutputImageType": [C.c_int, C.c_int],
            "SVBSetControlValue": [C.c_int, C.c_int, C.c_long, C.c_int],
            "SVBGetControlValue": [C.c_int, C.c_int, C.POINTER(C.c_long), C.POINTER(C.c_int)],
            "SVBStartVideoCapture": [C.c_int],
            "SVBGetVideoData": [C.c_int, C.c_void_p, C.c_long, C.c_int],
            "SVBStopVideoCapture": [C.c_int],
        }
        for name, arguments in signatures.items():
            fn = getattr(self.lib, name)
            fn.argtypes = arguments
            fn.restype = C.c_int
        self.camera_id = None
        self.opened = False
        self.streaming = False
        self.original_controls = {}

    def _ok(self, method, *args):
        code = getattr(self.lib, method)(*args)
        if code != 0:
            raise SDKError(method, code)

    def read_control(self, control):
        value, auto = C.c_long(), C.c_int()
        self._ok("SVBGetControlValue", self.camera_id, control, C.byref(value), C.byref(auto))
        return value.value, auto.value

    def set_control(self, control, value):
        self._ok("SVBSetControlValue", self.camera_id, control, int(value), 0)
        return self.read_control(control)[0]

    def open(self):
        count = self.lib.SVBGetNumOfConnectedCameras()
        if count != 1:
            raise RuntimeError(f"Expected one SVBONY camera, SDK found {count}")
        info = CameraInfo()
        self._ok("SVBGetCameraInfo", C.byref(info), 0)
        self.camera_id = info.CameraID
        try:
            self._ok("SVBOpenCamera", self.camera_id)
            self.opened = True
            for control in (GAIN, EXPOSURE):
                self.original_controls[control] = self.read_control(control)
            self._ok("SVBSetROIFormat", self.camera_id, 0, 0, WIDTH, HEIGHT, 1)
            self._ok("SVBSetOutputImageType", self.camera_id, RAW16)
        except Exception:
            self.close()
            raise

    def start(self):
        self._ok("SVBStartVideoCapture", self.camera_id)
        self.streaming = True

    def get_frame(self, buffer, wait_ms):
        self._ok("SVBGetVideoData", self.camera_id, C.cast(buffer, C.c_void_p),
                 RAW_BYTES, int(wait_ms))

    def close(self):
        if not self.opened:
            self.camera_id = None
            return
        if self.streaming:
            try:
                self._ok("SVBStopVideoCapture", self.camera_id)
            except SDKError:
                pass
            self.streaming = False
        for control, (value, automatic) in self.original_controls.items():
            try:
                self._ok("SVBSetControlValue", self.camera_id, control, value, automatic)
            except SDKError:
                pass
        try:
            self._ok("SVBCloseCamera", self.camera_id)
        except SDKError:
            pass
        self.camera_id = None
        self.opened = False
