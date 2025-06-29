import json as _json
import os
import re
from pathlib import Path
from typing import Dict, Tuple

import toml

config = dict  # autocomplete


def crawl(obj: dict, func=lambda x, y: print(x, y, end="\n"), path=None):
    if path is None:  # path Default argument value is mutable
        path = []
    for key in obj.keys():
        if type(obj[key]) is dict:
            crawl(obj[key], func, path + [key])
            continue
        func(path + [key], obj[key])


def check(value, checks, name):

    def get_check_value(key, default_result):
        return checks[key] if key in checks else default_result

    incorrect = False
    if value == {}:
        print(f"DEBUG: Value for {name} is an empty dict and triggers incorrect.")
        incorrect = True
    if not incorrect and "type" in checks:
        try:
            value = eval(checks["type"])(value)
        except Exception as e:
            print(f"DEBUG: Value for {name} failed type check ({checks['type']}): {value} ({e})")
            incorrect = True
    # FAILSTATE Value is not one of the options
    if not incorrect and "options" in checks and value not in checks["options"]:
        print(f"DEBUG: Value for {name} not in options {checks['options']}: {value}")
        incorrect = True
    # FAILSTATE Value doesn't match regex, or has regex but is not a string.
    if (
        not incorrect
        and "regex" in checks
        and (
            (isinstance(value, str) and re.match(checks["regex"], value) is None)
            or not isinstance(value, str)
        )
    ):
        print(f"DEBUG: Value for {name} failed regex {checks['regex']}: {value}")
        incorrect = True

    if (
        not incorrect
        and not hasattr(value, "__iter__")
        and (
            ("nmin" in checks and checks["nmin"] is not None and value < checks["nmin"])
            or (
                "nmax" in checks
                and checks["nmax"] is not None
                and value > checks["nmax"]
            )
        )
    ):
        print(f"DEBUG: Value for {name} failed numeric bounds nmin/nmax: {value}, checks: {checks}")
        incorrect = True
    if (
        not incorrect
        and hasattr(value, "__iter__")
        and (
            (
                "nmin" in checks
                and checks["nmin"] is not None
                and len(value) < checks["nmin"]
            )
            or (
                "nmax" in checks
                and checks["nmax"] is not None
                and len(value) > checks["nmax"]
            )
        )
    ):
        print(f"DEBUG: Value for {name} failed length bounds nmin/nmax: {value}, checks: {checks}")
        incorrect = True

    if incorrect:
        value = handle_input(
            message=(
                (
                    ("\nExample: " + str(checks["example"]) + "\n")
                    if "example" in checks
                    else ""
                )
                + ("Non-optional ", "Optional ")[
                    "optional" in checks and checks["optional"] is True
                ]
            )
            + str(name),
            extra_info=get_check_value("explanation", ""),
            check_type=eval(get_check_value("type", "False")),
            default=get_check_value("default", NotImplemented),
            match=get_check_value("regex", ""),
            err_message=get_check_value("input_error", "Incorrect input"),
            nmin=get_check_value("nmin", None),
            nmax=get_check_value("nmax", None),
            oob_error=get_check_value(
                "oob_error", "Input out of bounds(Value too high/low/long/short)"
            ),
            options=get_check_value("options", None),
            optional=get_check_value("optional", False),
        )
    return value


def handle_input(
    message: str = "",
    check_type=False,
    match: str = "",
    err_message: str = "",
    nmin=None,
    nmax=None,
    oob_error="",
    extra_info="",
    options: list = None,
    default=NotImplemented,
    optional=False,
):
    if optional:
        print(message + "\nThis is an optional value. Do you want to skip it? (y/n)")
        if input().casefold().startswith("y"):
            return default if default is not NotImplemented else ""
    if default is not NotImplemented:
        print(
            message
            + '\nThe default value is "'
            + str(default)
            + '"\nDo you want to use it?(y/n)'
        )
        if input().casefold().startswith("y"):
            return default
    if options is None:
        match = re.compile(match)
        print(extra_info)
        while True:
            print(message + "=", end="")
            user_input = input("").strip()
            if check_type is not False:
                try:
                    user_input = check_type(user_input)
                    if (nmin is not None and user_input < nmin) or (
                        nmax is not None and user_input > nmax
                    ):
                        # FAILSTATE Input out of bounds
                        print(oob_error)
                        continue
                    break  # Successful type conversion and number in bounds
                except ValueError:
                    # Type conversion failed
                    print(err_message)
                    continue
            elif match != "" and re.match(match, user_input) is None:
                print(+err_message + "\nAre you absolutely sure it's correct?(y/n)")
                if input().casefold().startswith("y"):
                    break
                continue
            else:
                # FAILSTATE Input STRING out of bounds
                if (nmin is not None and len(user_input) < nmin) or (
                    nmax is not None and len(user_input) > nmax
                ):
                    print(oob_error)
                    continue
                break  # SUCCESS Input STRING in bounds
        return user_input
    print(extra_info)
    while True:
        print(message, end="")
        user_input = input("").strip()
        if check_type is not False:
            try:
                isinstance(eval(user_input), check_type)
                return check_type(user_input)
            except:
                print(
                    err_message
                    + "\nValid options are: "
                    + ", ".join(map(str, options))
                    + "."
                )
                continue
        if user_input in options:
            return user_input
        print(
            err_message + "\nValid options are: " + ", ".join(map(str, options)) + "."
        )


def crawl_and_check(obj: dict, path: list, checks: dict = {}, name=""):
    if len(path) == 0:
        return check(obj, checks, name)
    if path[0] not in obj.keys():
        obj[path[0]] = {}
    obj[path[0]] = crawl_and_check(obj[path[0]], path[1:], checks, path[0])
    return obj


def check_vars(path, checks):
    global config
    crawl_and_check(config, path, checks)


def check_toml(template_file, config_file) -> Tuple[bool, Dict]:
    global config, check_vars
    config = None

    # attempt to load template file
    try:
        template = toml.load(template_file)
    except Exception as error:
        print(f"Encountered error when trying to to load {template_file}: {error}")
        print(error)
        return False

    # attempt to config template file
    try:
        config = toml.load(config_file)
    # if file can't be read
    except toml.TomlDecodeError:
        print(f"""Couldn't read {config_file}.Overwrite it?(y/n)""")
        # attempt to overwrite config file
        if not input().startswith("y"):
            print("Unable to read config, and not allowed to overwrite it. Giving up.")
            return False
        else:
            try:
                with open(config_file, "w") as f:
                    f.write("")
            except:
                print(
                    f"Failed to overwrite {config_file}. Giving up.\nSuggestion: check {config_file} permissions for the user."
                )
                return False
    # if file isn't found
    except FileNotFoundError:
        print(f"""Couldn't find {config_file} Creating it now.""")
        try:
            with open(config_file, "x") as f:
                f.write("")
            config = {}
        except:
            print(
                f"Failed to write to {config_file}. Giving up.\nSuggestion: check the folder's permissions for the user."
            )
            return False

    crawl(template, check_vars)
    with open(config_file, "w") as f:
        toml.dump(config, f)
    return config


# Get the directory where this file (config.toml) is located
base_dir = Path(__file__).parent.parent 
template_path = base_dir / "utils" / ".config.template.toml"
config_path = base_dir / "config.toml"
check_toml(str(template_path), str(config_path))


