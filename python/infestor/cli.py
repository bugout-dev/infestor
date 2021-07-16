"""
Command line interface for the Humbug infestor.
"""
import argparse
import os
from typing import Callable, Tuple

from . import config, operations

CLIHandler = Callable[[argparse.Namespace], None]


def handle_config_init(args: argparse.Namespace) -> None:
    config.initialize(
        args.repository,
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
    config_object = config.set_reporter_token(
        config_file,
        args.token,
    )

    if config_object.reporter_filepath is not None:
        operations.add_reporter(
            args.repository,
            config_object.reporter_filepath,
            force=True,
        )

    print(config_object)


def handle_reporter_add(args: argparse.Namespace) -> None:
    operations.add_reporter(args.repository, args.reporter_filepath, args.force)


def handle_report_all(args: argparse.Namespace) -> None:
    operations.add_call(operations.CALL_TYPE_SYSTEM_REPORT, args.repository)
    operations.add_call(operations.CALL_TYPE_SETUP_EXCEPTHOOK, args.repository)

    files = operations.python_files(args.repository)
    for file in files:
        candidates = operations.decorator_candidates(
            operations.DECORATOR_TYPE_RECORD_ERRORS, args.repository, file
        )
        candidate_linenos = []
        for candidate in candidates:
            candidate_linenos.append(candidate.lineno)
        if candidate_linenos:
            operations.add_decorators(
                operations.DECORATOR_TYPE_RECORD_ERRORS,
                args.repository,
                file,
                candidate_linenos,
            )
    for file in files:
        candidates = operations.decorator_candidates(
            operations.DECORATOR_TYPE_RECORD_CALL, args.repository, file
        )
        candidate_linenos = []
        for candidate in candidates:
            candidate_linenos.append(candidate.lineno)
        if candidate_linenos:
            operations.add_decorators(
                operations.DECORATOR_TYPE_RECORD_CALL,
                args.repository,
                file,
                candidate_linenos,
            )


def generate_call_handlers(call_type: str) -> Tuple[CLIHandler, CLIHandler, CLIHandler]:
    """
    Returns a tuple of the form:
    (handle_list, handle_add, handle_remove)
    """

    def handle_list(args: argparse.Namespace) -> None:
        results = operations.list_calls(call_type, args.repository)
        for filepath, calls in results.items():
            print(f"Lines in {filepath}:")
            for call in calls:
                print(f"\t- (line {call.lineno}) {call.scope_stack}")

    def handle_add(args: argparse.Namespace) -> None:
        # TODO(zomglings): Is there a better way to check if an argparse.Namespace has a given member?
        if vars(args).get("submodule") is not None:
            operations.add_call(call_type, args.repository, args.submodule)
        else:
            operations.add_call(call_type, args.repository)

    def handle_remove(args: argparse.Namespace) -> None:
        # TODO(zomglings): Ditto
        if vars(args).get("submodule") is not None:
            operations.remove_calls(call_type, args.repository, args.submodule)
        else:
            operations.remove_calls(call_type, args.repository)

    return (handle_list, handle_add, handle_remove)


def generate_decorator_handlers(
    decorator_type: str,
) -> Tuple[CLIHandler, CLIHandler, CLIHandler, CLIHandler]:
    """
    Returns a tuple of the form:
    (handle_list, handle_candidates, handle_add, handle_remove)
    """

    def handle_list(args: argparse.Namespace) -> None:
        results = operations.list_decorators(decorator_type, args.repository)
        for filepath, decorators in results.items():
            print(f"Lines in {filepath}:")
            for decorator in decorators:
                print(f"\t- (line {decorator.lineno}) {decorator.scope_stack}")

    def handle_candidates(args: argparse.Namespace) -> None:
        results = operations.decorator_candidates(
            decorator_type, args.repository, args.submodule
        )
        print(f"You can add the {decorator_type} decorator to the following functions:")
        for candidate in results:
            print(f"\t- (line {candidate.lineno}) {candidate.scope_stack}")

    def handle_add(args: argparse.Namespace) -> None:
        operations.add_decorators(
            decorator_type,
            args.repository,
            args.submodule,
            args.lines,
        )

    def handle_remove(args: argparse.Namespace) -> None:
        operations.remove_decorators(
            decorator_type,
            args.repository,
            args.submodule,
            args.lines,
        )

    return (handle_list, handle_candidates, handle_add, handle_remove)


def generate_argument_parser() -> argparse.ArgumentParser:
    current_working_directory = os.getcwd()

    parser = argparse.ArgumentParser(
        description="Infestor: Manage Humbug instrumentation of your Python code base"
    )
    parser.set_defaults(func=lambda _: parser.print_help())
    subcommands = parser.add_subparsers()

    def populate_leaf_parser_with_common_args(
        leaf_parser: argparse.ArgumentParser,
    ) -> None:
        leaf_parser.add_argument(
            "-r",
            "--repository",
            default=current_working_directory,
            help=f"Path to git repository containing your code base (default: {current_working_directory})",
        )

    config_parser = subcommands.add_parser(
        "config", description="Manage infestor configuration"
    )
    config_parser.set_defaults(func=lambda _: config_parser.print_help())
    config_subcommands = config_parser.add_subparsers()

    config_init_parser = config_subcommands.add_parser(
        "init", description="Initialize an Infestor integration in a project"
    )
    populate_leaf_parser_with_common_args(config_init_parser)
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
    populate_leaf_parser_with_common_args(config_validate_parser)
    config_validate_parser.set_defaults(func=handle_config_validate)

    config_token_parser = config_subcommands.add_parser(
        "token", description="Set a Humbug token for an Infestor integration"
    )
    populate_leaf_parser_with_common_args(config_token_parser)
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
    populate_leaf_parser_with_common_args(reporter_add_parser)
    reporter_add_parser.add_argument(
        "-o",
        "--reporter-filepath",
        required=False,
        default=operations.DEFAULT_REPORTER_FILENAME,
        help=f"Path (relative to Python root) at which we should set up the reporter integration (default: {operations.DEFAULT_REPORTER_FILENAME})",
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

    (
        handle_system_report_list,
        handle_system_report_add,
        handle_system_report_remove,
    ) = generate_call_handlers(operations.CALL_TYPE_SYSTEM_REPORT)

    system_report_list_parser = system_report_subcommands.add_parser(
        "list",
        description="Adds reporting code to a given module",
    )
    populate_leaf_parser_with_common_args(system_report_list_parser)
    system_report_list_parser.set_defaults(func=handle_system_report_list)

    system_report_add_parser = system_report_subcommands.add_parser(
        "add",
        description="Adds reporting code to a given module",
    )
    populate_leaf_parser_with_common_args(system_report_add_parser)
    system_report_add_parser.add_argument(
        "-m",
        "--submodule",
        default=None,
        help="Path (relative to Python root) to submodule in which to fire off a system report",
    )
    system_report_add_parser.set_defaults(func=handle_system_report_add)

    system_report_remove_parser = system_report_subcommands.add_parser(
        "remove", description="Removes reporting code from a given module"
    )
    populate_leaf_parser_with_common_args(system_report_remove_parser)
    system_report_remove_parser.add_argument(
        "-m",
        "--submodule",
        default=None,
        help="Path (relative to Python root) to submodule in which to fire off a system report",
    )
    system_report_remove_parser.set_defaults(func=handle_system_report_remove)

    excepthook_parser = subcommands.add_parser(
        "excepthook", description="Manage crash reporting (of all uncaught exceptions)"
    )
    excepthook_parser.set_defaults(func=lambda _: excepthook_parser.print_help())
    excepthook_subcommands = excepthook_parser.add_subparsers()

    (
        handle_excepthook_list,
        handle_excepthook_add,
        handle_excepthook_remove,
    ) = generate_call_handlers(operations.CALL_TYPE_SETUP_EXCEPTHOOK)

    excepthook_list_parser = excepthook_subcommands.add_parser(
        "list",
        description="Adds reporting code to a given module",
    )
    populate_leaf_parser_with_common_args(excepthook_list_parser)
    excepthook_list_parser.set_defaults(func=handle_excepthook_list)

    excepthook_add_parser = excepthook_subcommands.add_parser(
        "add",
        description="Adds crash reporting to a given package",
    )
    populate_leaf_parser_with_common_args(excepthook_add_parser)
    excepthook_add_parser.set_defaults(func=handle_excepthook_add)

    excepthook_remove_parser = excepthook_subcommands.add_parser(
        "remove",
        description="Adds crash reporting to a given package",
    )
    populate_leaf_parser_with_common_args(excepthook_remove_parser)
    excepthook_remove_parser.set_defaults(func=handle_excepthook_remove)

    record_call_parser = subcommands.add_parser(
        "record-call", description="Record every time a function/method is called"
    )
    record_call_parser.set_defaults(func=lambda _: record_call_parser.print_help())
    record_call_subcommands = record_call_parser.add_subparsers()

    (
        handle_record_call_list,
        handle_record_call_candidates,
        handle_record_call_add,
        handle_record_call_remove,
    ) = generate_decorator_handlers(operations.DECORATOR_TYPE_RECORD_CALL)

    record_call_list_parser = record_call_subcommands.add_parser(
        "list",
        description="List all functions/methods which are currently being recorded",
    )
    populate_leaf_parser_with_common_args(record_call_list_parser)
    record_call_list_parser.set_defaults(func=handle_record_call_list)

    record_call_candidates_parser = record_call_subcommands.add_parser(
        "candidates",
        description="List all functions/methods in the given submodule on which we can add the decorator",
    )
    populate_leaf_parser_with_common_args(record_call_candidates_parser)
    record_call_candidates_parser.add_argument(
        "-m",
        "--submodule",
        required=True,
        help="Path (relative to Python root) to submodule in which list candidates",
    )
    record_call_candidates_parser.set_defaults(func=handle_record_call_candidates)

    record_call_add_parser = record_call_subcommands.add_parser(
        "add",
        description="Adds reporting code to a given module",
    )
    populate_leaf_parser_with_common_args(record_call_add_parser)
    record_call_add_parser.add_argument(
        "-m",
        "--submodule",
        required=True,
        help="Path (relative to Python root) to submodule in which list candidates",
    )
    record_call_add_parser.add_argument(
        "lines",
        type=int,
        nargs="+",
        help="Line numbers of function definitions to decorate",
    )
    record_call_add_parser.set_defaults(func=handle_record_call_add)

    record_call_remove_parser = record_call_subcommands.add_parser(
        "remove",
        description="List all functions/methods which are currently being recorded",
    )
    populate_leaf_parser_with_common_args(record_call_remove_parser)
    record_call_remove_parser.add_argument(
        "-m",
        "--submodule",
        required=True,
        help="Path (relative to Python root) to submodule in which list candidates",
    )
    record_call_remove_parser.add_argument(
        "lines",
        type=int,
        nargs="+",
        help="Line numbers of function definitions to decorate",
    )
    record_call_remove_parser.set_defaults(func=handle_record_call_remove)

    record_error_parser = subcommands.add_parser(
        "record-error",
        description="Record function/method's caught and uncaught errors",
    )
    record_error_parser.set_defaults(func=lambda _: record_error_parser.print_help())
    record_error_subcommands = record_error_parser.add_subparsers()

    (
        handle_record_error_list,
        handle_record_error_candidates,
        handle_record_error_add,
        handle_record_error_remove,
    ) = generate_decorator_handlers(operations.DECORATOR_TYPE_RECORD_ERRORS)

    record_error_list_parser = record_error_subcommands.add_parser(
        "list",
        description="List all functions/methods which are currently being recorded",
    )
    populate_leaf_parser_with_common_args(record_error_list_parser)
    record_error_list_parser.set_defaults(func=handle_record_error_list)

    record_error_candidates_parser = record_error_subcommands.add_parser(
        "candidates",
        description="List all functions/methods in the given submodule on which we can add the decorator",
    )
    populate_leaf_parser_with_common_args(record_error_candidates_parser)
    record_error_candidates_parser.add_argument(
        "-m",
        "--submodule",
        required=True,
        help="Path (relative to Python root) to submodule in which list candidates",
    )
    record_error_candidates_parser.set_defaults(func=handle_record_error_candidates)

    record_error_add_parser = record_error_subcommands.add_parser(
        "add",
        description="Adds reporting code to a given module",
    )
    populate_leaf_parser_with_common_args(record_error_add_parser)
    record_error_add_parser.add_argument(
        "-m",
        "--submodule",
        required=True,
        help="Path (relative to Python root) to submodule in which list candidates",
    )
    record_error_add_parser.add_argument(
        "lines",
        type=int,
        nargs="+",
        help="Line numbers of function definitions to decorate",
    )
    record_error_add_parser.set_defaults(func=handle_record_error_add)

    record_error_remove_parser = record_error_subcommands.add_parser(
        "remove",
        description="List all functions/methods which are currently being recorded",
    )
    populate_leaf_parser_with_common_args(record_error_remove_parser)
    record_error_remove_parser.add_argument(
        "-m",
        "--submodule",
        required=True,
        help="Path (relative to Python root) to submodule in which list candidates",
    )
    record_error_remove_parser.add_argument(
        "lines",
        type=int,
        nargs="+",
        help="Line numbers of function definitions to decorate",
    )
    record_error_remove_parser.set_defaults(func=handle_record_error_remove)

    report_all_parser = subcommands.add_parser(
        "report-all", description="Report all that can be reported "
    )
    populate_leaf_parser_with_common_args(report_all_parser)
    report_all_parser.set_defaults(func=handle_report_all)

    return parser


def main() -> None:
    parser = generate_argument_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
