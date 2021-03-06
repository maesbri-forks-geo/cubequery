import json
import logging
import os
import zipfile
from enum import EnumMeta
from os import path

import datacube
from jobtastic import JobtasticTask
from shapely import wkt

from cubequery import get_config
from cubequery.utils.s3_tools import S3Utils


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
    def __init__(self, name, display_name, d_type, description, valid=None):
        if valid is None:
            valid = []
        self.name = name
        self.display_name = display_name
        self.d_type = d_type
        self.description = description
        self.valid = valid


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
            return str
        if d_type in (DType.FLOAT, DType.LAT, DType.LON):
            return str
        return str

    def map_kwargs(self, **kwargs):
        result = {}
        for k, v in kwargs.items():
            args = [p for p in self.parameters if p.name == k]
            if len(args) > 0:
                arg = args[0]
                if arg.d_type == DType.INT:
                    result[k] = int(v)
                elif arg.d_type in (DType.FLOAT, DType.LAT, DType.LON):
                    result[k] = float(v)
                else:
                    result[k] = v
            else:
                result[k] = v
        return result

    def validate_arg(self, name, value):
        search = [p for p in self.parameters if p.name == name]
        if len(search) == 0:
            return False, f"parameter {name} not found"

        param = search[0]
        if not validate_d_type(param, value):
            return False, f"parameter {name} value did not validate"
        return True, ""

    def calculate_result(self, **kwargs):
        """
        This is the entry point for a task run. Will be called by celery.

        :param kwargs: arguments to the tasks.
        :return:
        """

        # connect to the datacube and pass that in to the users function.
        # Everything should be talking to the datacube here so makes sense to pull it out and make things
        # easier for the users.
        result_dir = get_config("App", "result_dir")
        path_prefix = path.join(result_dir, self.request.id)

        os.makedirs(path_prefix, exist_ok=True)

        dc = datacube.Datacube(app=self.name)
        outputs = self.generate_product(dc, path_prefix, **self.map_kwargs(**kwargs))
        logging.info(f"got result of {outputs}")
        self.log_query(path_prefix)
        self.zip_outputs(path_prefix, outputs)
        # TODO: put the results some where, send notifications etc.
        output_url = self.upload_results(path_prefix)

        self.ping_results(output_url)

    def log_query(self, path_prefix):
        output = path.join(path_prefix, "query.json")
        with open(output, 'w') as f:
            json.dump(self.request.__dict__, f, skipkeys=True)

    def zip_outputs(self, path_prefix, results):
        output = os.path.join(path_prefix, self.request.id + "_output.zip")
        with zipfile.ZipFile(output, 'w') as zf:
            zf.write(path.join(path_prefix, "query.json"), arcname="query.json")
            for f in results:
                zf.write(f, arcname=path.basename(f))

    def upload_results(self, path_prefix):
        source_file_path = os.path.join(path_prefix, self.request.id + "_output.zip")
        dest_file_path = os.path.join(get_config("AWS", "path_prefix"), self.request.id + "_output.zip")

        access_key = get_config("AWS", "access_key_id")
        secret_key = get_config("AWS", "secret_access_key")
        bucket = get_config("AWS", "bucket")

        s3_tools = S3Utils(access_key, secret_key, bucket, get_config("AWS", "end_point"), get_config("AWS", "region"))

        s3_tools.put_file(source_file_path, dest_file_path)

        return dest_file_path

    def ping_results(self, output_url):
        result_url = get_config("App", "result_url")
        if result_url:
            payload = {
                "url": output_url,
                "name": ""
            }
            print(payload)

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
    if param.d_type == DType.WKT:
        # try and parse it and see what happens
        try:
            wkt.loads(value)
            return True
        except Exception:
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
