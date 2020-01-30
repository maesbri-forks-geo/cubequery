from enum import EnumMeta

from jobtastic import JobtasticTask


class DType(EnumMeta):
    STRING = "str"
    INT = "int"
    FLOAT = "float"
    LAT = "lat"
    LON = "lon"
    DATE = "date"
    TIME = "time"
    WKT = "wkt"


class Parameter(object):
    def __init__(self, name, d_type, description):
        self.name = name
        self.d_type = d_type
        self.description = description


class CubeQueryTask(JobtasticTask):

    @classmethod
    def cal_significant_kwargs(cls, parameters):
        result = []
        for p in parameters:
            result += [(p.name, cls.map_d_type_to_jobtastic(p.d_type))]
        cls.significant_kwargs = result
        return result

    @classmethod
    def map_d_type_to_jobtastic(cls, d_type):
        # TODO: add more data types here.
        # special handling for dates, lat lon pairs, bounding boxes, etc.
        if d_type == DType.INT:
            return int
        return str

    def validate_arg(self, name, value):
        # TODO: Make this return a message to be more useful
        search = [p for p in self.parameters if p.name == name]
        if len(search) == 0:
            return False

        param = search[0]
        # TODO: validate data type of value
        if not validate_d_type(param, value):
            return False
        # TODO: check ranges
        return True

    herd_avoidance_timeout = 60
    cache_duration = 60 * 60 * 24  # One day of seconds


def validate_d_type(param, value):
    if param.d_type == DType.INT:
        return check_int(value)
    if param.d_type == DType.FLOAT:
        return check_float(value)
    if param.d_type == DType.LAT:
        if check_float(value):
            v = float(value)
            return -90.0 <= v <= 90.0
        return False
    if param.d_type == DType.LON:
        if check_float(value):
            v = float(value)
            return -180.0 <= v <= 180.0
        return False
    # if it is not one of the above types we can just check it is a string for now.
    # TODO: More type validations. WKT, DateFormats etc.
    return isinstance(value, str)


def check_int(s):
    if isinstance(s, int):
        return True
    if isinstance(s, str):
        if len(s) == 0:
            return False
        if s[0] in ('-', '+'):
            return s[1:].isdigit()

        return s.isdigit()
    return False


def check_float(s):
    if isinstance(s, float):
        return True
    try:
        float(s)
        return True
    except ValueError:
        return False
