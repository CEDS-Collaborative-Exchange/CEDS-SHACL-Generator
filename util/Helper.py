import inspect
import logging
from typing import List
import json

from util import LogUtil

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)
logger = LogUtil.create_logger(__name__)

def to_string(clazz):
    class_members = inspect.getmembers(clazz)

    buffer = []
    for name,anyObj in class_members:
        if not name.startswith("__"):
            buffer.append(name)
            buffer.append(",")
    return str(buffer)


# Custom serialization function
def custom_serializer(obj):
    if hasattr(obj, "__dict__"):
        return getattr(obj, "__dict__")
    else:
        raise TypeError(f"Type {type(obj)} not serializable")

def to_json(clazz_list:List[any]):
    for iter_obj in clazz_list:
        json_val = None#json.dumps(iter_obj, default=lambda obj: obj.__dict__, indent=4)
        if hasattr(iter_obj,"__dict__"):
            json_val = json.dumps(iter_obj,default=custom_serializer(iter_obj),indent=4)
        logger.info('json_val:%s',json_val)
    return None