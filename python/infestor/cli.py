"""
Command line interface for the Humbug infestor.
"""
import argparse
import os
import sys

from . import config, manage


def handle_config_init(args: argparse.Namespace) -> None:
    config.initialize(
        args.repository,
        args.python_root,
        args.name,
        args.relative_imports,
        args.reporter_token,
    )
    print("Infestor has been initialized for your repository.\n")

    print(
        "The Bugout team would like to collect crash reports as well as some basic, anonymous "
        "information about your system when you run infestor.\nThis will help us improve the "
        "infestor experience for everyone.\nWe request that you opt into reporting by setting the "
        "environment variable:\n"
        "\tINFESTOR_REPORTING_ENABLED=yes\n"
    )
    print("In bash or zsh:\n\t$ export INFESTOR_REPORTING_ENABLED=yes")
    print("In fish:\n\t$ set -x INFESTOR_REPORTING_ENABLED yes")
    print("On Windows (cmd or powershell):\n\t$ set INFESTOR_REPORTING_ENABLED=yes\n")

    if args.reporter_token is None:
        print(
            "It looks like you have not configured Infestor with a Bugout reporter token."
        )
        print(
            "Generate a reporter token by adding an integration to your team at https://bugout.dev/account/teams."
        )
        print("Once you have generated a token, run:")
        print("\t$ infestor token <token>\n")


def handle_config_validate(args: argparse.Namespace) -> None:
    config_file = config.default_config_file(args.repository)
    config.load_config(config_file, print_warnings=True)


def handle_config_token(args: argparse.Namespace) -> None:
    config_file = config.default_config_file(args.repository)
    python_root = config.python_root_relative_to_repository_root(
        args.repository, args.python_root
    )

    config_object = config.set_reporter_token(
        config_file,
        python_root,
        args.token,
    )

    manage.add_reporter(
        args.repository,
        python_root,
        config_object[python_root].reporter_filepath,
        force=True,
    )

    print(config_object)


def handle_reporter_add(args: argparse.Namespace) -> None:
    manage.add_reporter(
        args.repository, args.python_root, args.reporter_filepath, args.force
    )


def handle_system_report_add(args: argparse.Namespace) -> None:
    manage.add_system_report(args.repository, args.python_root, args.submodule)


def handle_system_report_list(args: argparse.Namespace) -> None:
    results = manage.list_system_reports(args.repository, args.python_root)
    for filepath, calls in results.items():
        print(f"Lines in {filepath}:")
        for report_call in calls:
            print(f"\t- {report_call.lineno}")


def handle_system_report_remove(args: argparse.Namespace) -> None:
    manage.remove_system_report(args.repository, args.python_root, args.submodule)


def generate_argument_parser() -> argparse.ArgumentParser:
    current_working_directory = os.getcwd()

    parser = argparse.ArgumentParser(
        description="Infestor: Manage Humbug instrumentation of your Python code base"
    )
    parser.set_defaults(func=lambda _: parser.print_help())
    subcommands = parser.add_subparsers()

    config_parser = subcommands.add_parser(
        "config", description="Manage infestor configuration"
    )
    config_parser.set_defaults(func=lambda _: config_parser.print_help())
    config_subcommands = config_parser.add_subparsers()

    config_init_parser = config_subcommands.add_parser(
        "init", description="Initialize an Infestor integration in a project"
    )
    config_init_parser.add_argument(
        "-r",
        "--repository",
        default=current_working_directory,
        help=f"Path to git repository containing your code base (default: {current_working_directory})",
    )
    config_init_parser.add_argument(
        "-P",
        "--python-root",
        required=True,
        help=(
            "Root directory for Python code/module in the repository. If you are integrating with "
            "a module, this will be the highest-level directory with an __init__.py file in it."
        ),
    )
    config_init_parser.add_argument(
        "-n",
        "--name",
        required=True,
        help="Name of project (to identify integration)",
    )
    config_init_parser.add_argument(
        "--relative-imports",
        action="store_true",
        help="Set this flags if infestor should add relative imports.",
    )
    config_init_parser.add_argument(
        "-t",
        "--reporter-token",
        default=None,
        help="Bugout reporter token. Get one by setting up an integration at https://bugout.dev/account/teams",
    )
    config_init_parser.set_defaults(func=handle_config_init)

    config_validate_parser = config_subcommands.add_parser(
        "validate", description="Validate an Infestor configuration"
    )
    config_validate_parser.add_argument(
        "-r",
        "--repository",
        default=current_working_directory,
        help=f"Path to git repository containing your code base (default: {current_working_directory})",
    )
    config_validate_parser.set_defaults(func=handle_config_validate)

    config_token_parser = config_subcommands.add_parser(
        "token", description="Set a Humbug token for an Infestor integration"
    )
    config_token_parser.add_argument(
        "-r",
        "--repository",
        default=current_working_directory,
        help=f"Path to git repository containing your code base (default: {current_working_directory})",
    )
    config_token_parser.add_argument(
        "-P",
        "--python-root",
        required=True,
        help="Root directory for Python code/module you want to register a token for (this is the relevant key in infestor.json)",
    )
    config_token_parser.add_argument(
        "token", help="Reporting token generated from https://bugout.dev/account/teams"
    )
    config_token_parser.set_defaults(func=handle_config_token)

    reporter_parser = subcommands.add_parser(
        "reporter", description="Manage Humbug reporters in a code base"
    )
    reporter_parser.set_defaults(func=lambda _: reporter_parser.print_help())
    reporter_subcommands = reporter_parser.add_subparsers()

    reporter_add_parser = reporter_subcommands.add_parser(
        "add", description="Adds a Humbug reporter to a Python package"
    )
    reporter_add_parser.add_argument(
        "-r",
        "--repository",
        default=current_working_directory,
        help=f"Path to git repository containing your code base (default: {current_working_directory})",
    )
    reporter_add_parser.add_argument(
        "-P",
        "--python-root",
        required=True,
        help="Root directory for Python code/module you want to setup reporting for (this is the relevant key in infestor.json)",
    )
    reporter_add_parser.add_argument(
        "-o",
        "--reporter-filepath",
        required=False,
        default=manage.DEFAULT_REPORTER_FILENAME,
        help=f"Path (relative to Python root) at which we should set up the reporter integration (default: {manage.DEFAULT_REPORTER_FILENAME})",
    )
    reporter_add_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Set this flag if you want to overwrite the reporter file if it already exists",
    )
    reporter_add_parser.set_defaults(func=handle_reporter_add)

    system_report_parser = subcommands.add_parser(
        "system-report", description="Manage Humbug system reporting in a code base"
    )
    system_report_parser.set_defaults(func=lambda _: system_report_parser.print_help())
    system_report_subcommands = system_report_parser.add_subparsers()

    system_report_add_parser = system_report_subcommands.add_parser(
        "add",
        description="Adds reporting code to a given module",
    )
    system_report_add_parser.add_argument(
        "-r",
        "--repository",
        default=current_working_directory,
        help=f"Path to git repository containing your code base (default: {current_working_directory})",
    )
    system_report_add_parser.add_argument(
        "-P",
        "--python-root",
        required=True,
        help="Root directory for Python code/module you want to setup reporting for (this is the relevant key in infestor.json)",
    )
    system_report_add_parser.add_argument(
        "-m",
        "--submodule",
        default=None,
        help="Path (relative to Python root) to submodule in which to fire off a system report",
    )
    system_report_add_parser.set_defaults(func=handle_system_report_add)

    system_report_list_parser = system_report_subcommands.add_parser(
        "list",
        description="Adds reporting code to a given module",
    )
    system_report_list_parser.add_argument(
        "-r",
        "--repository",
        default=current_working_directory,
        help=f"Path to git repository containing your code base (default: {current_working_directory})",
    )
    system_report_list_parser.add_argument(
        "-P",
        "--python-root",
        required=True,
        help="Root directory for Python code/module you want to setup reporting for (this is the relevant key in infestor.json)",
    )
    system_report_list_parser.set_defaults(func=handle_system_report_list)

    system_report_remove_parser = system_report_subcommands.add_parser(
        "remove", description="Removes reporting code from a given module"
    )
    system_report_remove_parser.add_argument(
        "-r",
        "--repository",
        default=current_working_directory,
        help=f"Path to git repository containing your code base (default: {current_working_directory})",
    )
    system_report_remove_parser.add_argument(
        "-P",
        "--python-root",
        required=True,
        help="Root directory for Python code/module you want to setup reporting for (this is the relevant key in infestor.json)",
    )
    system_report_remove_parser.add_argument(
        "-m",
        "--submodule",
        default=None,
        help="Path (relative to Python root) to submodule in which to fire off a system report",
    )
    system_report_remove_parser.set_defaults(func=handle_system_report_remove)

    return parser


def main() -> None:
    parser = generate_argument_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
