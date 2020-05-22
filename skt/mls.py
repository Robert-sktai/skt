from pathlib import Path
from typing import List, Dict, Any
from enum import Enum

import requests
import json
import subprocess
import shlex
import os
import tarfile
import shutil
import re
from joblib import dump
from datetime import datetime

import lightgbm
import xgboost

from skt.vault_utils import get_secrets


MLS_MODEL_DIR = os.path.join(Path.home(), "mls_temp_dir")
MODEL_BINARY_NAME = "model.joblib"
MODEL_TAR_NAME = "model.tar.gz"
MODEL_META_NAME = "model.json"
S3_DEFAULT_PATH = "s3a://mls-model-registry"

EDD_OPTIONS = """-Dfs.s3a.proxy.host=awsproxy.datalake.net \
                 -Dfs.s3a.proxy.port=3128 \
                 -Dfs.s3a.endpoint=s3.ap-northeast-2.amazonaws.com \
                 -Dfs.s3a.security.credential.provider.path=jceks:///user/tairflow/s3_mls.jceks \
                 -Dfs.s3a.fast.upload=true -Dfs.s3a.acl.default=BucketOwnerFullControl"""


HEADER = {"Content-Type": "application/json"}
AB_URL_PREFIX = "https://ab-internal"
MLS_META_API_URL = "/api/v1/meta"


def set_model_name(comm_db, params):
    secret = get_secrets("mls")
    if comm_db[-3:] == "dev":  # stg
        url = secret["dev_url"]
    else:  # prd
        url = secret["prd_url"]
    requests.post(url, data=json.dumps(params))


def get_recent_model_path(comm_db, model_key):
    secret = get_secrets("mls")
    if comm_db[-3:] == "dev":  # stg
        url = secret["dev_url"]
    else:  # prd
        url = secret["prd_url"]
    return requests.get(f"{url}/latest").json()[model_key]


def get_model_name(key):
    secret = get_secrets("mls")
    url = secret["prd_url"]
    return requests.get(f"{url}/latest").json()[key]


class ModelLibrary(Enum):
    LIGHTGBM = "lightgbm"
    XGBOOST = "xgboost"


class AWSENV(Enum):
    STG = "stg"
    PRD = "prd"
    DEV = "dev"


class MLSModelError(Exception):
    def __init__(self, msg):
        super().__init__(msg)


def save_model(
    model,
    model_name: str,
    model_version: str,
    aws_env: AWSENV = AWSENV.STG.value,
    feature_list: List[str] = None,
    force: bool = False,
    edd: bool = False,
) -> None:
    """
    Upload model_binary(model.tar.gz) / model_meta(model.json) to AWS S3 from YE
    Args. :
        - model         :   Model object generated by LightGBM or XGBoost
        - model_name    :   (str) Model name to be saved on S3 and MLS
        - model_version :   (str) Model version to be saved on S3 ans MLS
        - aws_env       :   (str) AWS ENV in 'stg / prd / dev' (default is 'stg')
        - feature_list  :   (List[str]) List of features used in ML Model in string type (only for XGBoost model type)
        - force         :   (bool) Force to overwrite model files on S3 if exists (default is False)
        - edd           :   (bool) True if On-prem env is on EDD (default is False)
    """

    assert type(model_name) == str
    assert type(model_version) == str

    if not bool(re.search("^[A-Za-z0-9_]+_model$", model_name)):
        raise MLSModelError(
            "model_name should follow naming rule. MUST be in alphabet, number, underscore and endwiths '_model'"
        )

    if not bool(re.search("^[A-Za-z0-9_]+$", model_version)):
        raise MLSModelError("model_name should follow naming rule. MUST be in alphabet, number, underscore")

    def check_model_library(model):
        if isinstance(model, lightgbm.Booster):
            return ModelLibrary.LIGHTGBM.value, lightgbm.__version__
        elif isinstance(model, xgboost.XGBModel):
            return ModelLibrary.XGBOOST.value, xgboost.__version__
        else:
            raise MLSModelError("Input Model is none of LightGBM or XGBoost type")

    def get_feature_list(model, model_library: str):
        if model_library == ModelLibrary.LIGHTGBM.value:
            return model.feature_name()
        elif model_library == ModelLibrary.XGBOOST.value:
            if all(isinstance(s, str) for s in feature_list) and len(feature_list) == len(model.feature_importances_):
                return feature_list
            else:
                raise MLSModelError(
                    "Input feature list is not matching the number of model input feature or list STRING type"
                )

    model_library, model_library_version = check_model_library(model)
    feature_list = get_feature_list(model, model_library)

    s3_path = S3_DEFAULT_PATH
    if aws_env in (AWSENV.STG.value, AWSENV.PRD.value):
        s3_path = f"{S3_DEFAULT_PATH}-{aws_env}"
    s3_path = f"{s3_path}/{model_name}/{model_version}"

    model_meta = {
        "name": model_name,
        "version": model_version,
        "model_lib": model_library,
        "model_lib_version": model_library_version,
        "model_data": f"{s3_path}/{MODEL_TAR_NAME}",
        "features": feature_list,
    }

    model_path = os.path.join(
        MLS_MODEL_DIR, f"{aws_env}_{model_name}_{model_version}_{datetime.today().strftime('%Y%m%d_%H%M%S')}",
    )
    try:
        if not os.path.exists(os.path.join(model_path, MODEL_BINARY_NAME)):
            if not os.path.exists(model_path):
                os.makedirs(model_path)

            dump(model, os.path.join(model_path, MODEL_BINARY_NAME))
            with tarfile.open(f"{model_path}/{MODEL_TAR_NAME}", "w") as tar:
                tar.add(f"{model_path}/{MODEL_BINARY_NAME}")

            with open(os.path.join(model_path, MODEL_META_NAME), "w") as f:
                json.dump(model_meta, f)
        else:
            raise MLSModelError(f"{model_name} / {model_version} is already in PATH ({model_path})")

        cmd_mkdir = f"hdfs dfs {EDD_OPTIONS if edd else ''} -mkdir -p {s3_path}"
        cmd_load_model_to_s3 = f"hdfs dfs {EDD_OPTIONS if edd else ''} -put {'-f' if force else ''} \
            {os.path.join(model_path, MODEL_TAR_NAME)} {s3_path}"
        cmd_load_meta_to_s3 = f"hdfs dfs {EDD_OPTIONS if edd else ''} -put {'-f' if force else ''} \
            {os.path.join(model_path, MODEL_META_NAME)} {s3_path}"

        process_mkdir = subprocess.Popen(shlex.split(cmd_mkdir), stdout=subprocess.PIPE, stdin=subprocess.PIPE,)
        process_mkdir.wait()
        if process_mkdir.returncode != 0:
            raise MLSModelError(f"Making Directory on S3 ({s3_path}) is FAILED")

        process_model_binary = subprocess.Popen(
            shlex.split(cmd_load_model_to_s3), stdout=subprocess.PIPE, stdin=subprocess.PIPE,
        )
        process_model_binary.wait()
        if process_model_binary.returncode != 0:
            raise MLSModelError(
                f"Load model_binary(model.tar.gz) to S3 ({s3_path}) is FAILED. (Maybe Already exists on S3)"
            )

        process_model_meta = subprocess.Popen(
            shlex.split(cmd_load_meta_to_s3), stdout=subprocess.PIPE, stdin=subprocess.PIPE,
        )
        process_model_meta.wait()
        if process_model_meta.returncode != 0:
            raise MLSModelError(f"Load model_meta(meta.json) to S3 ({s3_path}) is FAILED")

    finally:
        shutil.rmtree(model_path, ignore_errors=True)


def get_meta_table(meta_table: str, aws_env: AWSENV = AWSENV.STG.value) -> Dict[str, Any]:
    """
    Get a meta_table information
    Args. :
        - meta_table   :   (str) the name of meta_table
        - aws_env      :   (str) AWS ENV in 'stg / prd / dev' (default is 'stg')
    Returns :
        - Dictionary value of meta_table (id / name / description / schema / items / created_at / updated_at)
    """
    assert type(meta_table) == str
    assert type(aws_env) == str

    url = AB_URL_PREFIX
    if aws_env in (AWSENV.STG.value, AWSENV.DEV.value):
        url = f"{url}.{aws_env}"
    url = f"{url}.sktmls.com{MLS_META_API_URL}/{meta_table}"

    response = requests.get(url).json()
    results = response.get("results")

    if not results:
        raise MLSModelError(response.get("error"))
    else:
        return results


def create_meta_table_item(
    meta_table: str, item_name: str, item_dict: Dict[str, Any], aws_env: AWSENV = AWSENV.STG.value
) -> None:
    """
    Create a meta_item
    Args. :
        - meta_table   :   (str) the name of meta_table
        - item_name    :   (str) the name of meta_item to be added
        - item_dict    :   (dict) A dictionary type (item-value) value to upload to or update of the item
        - aws_env      :   (str) AWS ENV in 'stg / prd / dev' (default is 'stg')
        - force        :   (bool) Force to overwrite(update) the item_meta value if already exists
    """
    assert type(meta_table) == str
    assert type(item_name) == str
    assert type(item_dict) == dict
    assert type(aws_env) == str

    meta_table_info = get_meta_table(meta_table, aws_env)

    values_data = dict()
    for field_name, field_spec in meta_table_info["schema"].items():
        values_data[field_name] = item_dict.get(field_name)

    request_data = dict()
    request_data["name"] = item_name
    request_data["values"] = values_data

    url = AB_URL_PREFIX
    if aws_env in (AWSENV.STG.value, AWSENV.DEV.value):
        url = f"{url}.{aws_env}"
    url = f"{url}.sktmls.com{MLS_META_API_URL}/{meta_table}/items"

    response = requests.post(url, headers=HEADER, data=json.dumps(request_data)).json()
    results = response.get("results")

    if not results:
        raise MLSModelError(response.get("error"))


def update_meta_table_item(
    meta_table: str, item_name: str, item_dict: Dict[str, Any], aws_env: AWSENV = AWSENV.STG.value
) -> None:
    """
    Update a meta_item
    Args. :
        - meta_table   :   (str) the name of meta_table
        - item_name    :   (str) the name of meta_item to be added
        - item_dict    :   (dict) A dictionary type (item-value) value to upload to or update of the item
        - aws_env      :   (str) AWS ENV in 'stg / prd / dev' (default is 'stg')
    """
    assert type(meta_table) == str
    assert type(item_name) == str
    assert type(item_dict) == dict
    assert type(aws_env) == str

    meta_table_info = get_meta_table(meta_table, aws_env)

    values_data = dict()
    for field_name, field_spec in meta_table_info["schema"].items():
        values_data[field_name] = item_dict.get(field_name)

    request_data = dict()
    request_data["name"] = item_name
    request_data["values"] = values_data

    url = AB_URL_PREFIX
    if aws_env in (AWSENV.STG.value, AWSENV.DEV.value):
        url = f"{url}.{aws_env}"
    url = f"{url}.sktmls.com{MLS_META_API_URL}/{meta_table}/items/{item_name}"

    response = requests.put(url, headers=HEADER, data=json.dumps(request_data)).json()
    results = response.get("results")

    if not results:
        raise MLSModelError(response.get("error"))


def get_meta_table_item(meta_table: str, item_name: str, aws_env: AWSENV = AWSENV.STG.value) -> Dict[str, Any]:
    """
    Get a meta_table information
    Args. :
        - meta_table   :   (str) the name of meta_table
        - item_name    :   (str) the name of meta_item to be added
        - aws_env      :   (str) AWS ENV in 'stg / prd / dev' (default is 'stg')
    Returns :
        - A dictionary type (item-value) value of the item_meta
    """
    assert type(meta_table) == str
    assert type(item_name) == str
    assert type(aws_env) == str

    url = AB_URL_PREFIX
    if aws_env in (AWSENV.STG.value, AWSENV.DEV.value):
        url = f"{url}.{aws_env}"
    url = f"{url}.sktmls.com{MLS_META_API_URL}/{meta_table}/items/{item_name}"

    response = requests.get(url).json()
    results = response.get("results")

    if not results:
        raise MLSModelError(response.get("error"))
    else:
        return results
