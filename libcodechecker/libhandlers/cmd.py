# -------------------------------------------------------------------------
#                     The CodeChecker Infrastructure
#   This file is distributed under the University of Illinois Open Source
#   License. See LICENSE.TXT for details.
# -------------------------------------------------------------------------
"""
The CodeChechecker command-line client can be used to view information about
analysis reports found on a running viewer 'server' from a command-line.
"""
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

import argparse
import getpass
import datetime
import sys

from libcodechecker import logger
from libcodechecker import output_formatters
from libcodechecker import util
from libcodechecker.cmd import cmd_line_client
from libcodechecker.cmd import product_client
from libcodechecker.cmd import source_component_client, token_client


DEFAULT_FILTER_VALUES = {
    'review_status': ['unreviewed', 'confirmed'],
    'detection_status': ['new', 'reopened', 'unresolved']
}


class NewLineDefaultHelpFormatter(argparse.ArgumentDefaultsHelpFormatter):

    def _split_lines(self, text, width):
        """
        Split a multi line string into multiple lines and wraps those lines so
        every line is at most 'width' character long.
        """
        lines = []
        for line in text.splitlines():
            w_lines = argparse.HelpFormatter._split_lines(self, line, width)
            for w_line in w_lines:
                lines.append(w_line)

        return lines


def valid_time(t):
    """
    Constructs a datetime from a 'year:month:day:hour:minute:second'-formatted
    string.
    """

    try:
        parts = map(int, t.split(':'))
        parts = parts + [0] * (6 - len(parts))
        year, month, day, hour, minute, second = parts
        return datetime.datetime(year, month, day, hour, minute, second)
    except ValueError as ex:
        raise argparse.ArgumentTypeError(ex)


def get_argparser_ctor_args():
    """
    This method returns a dict containing the kwargs for constructing an
    argparse.ArgumentParser (either directly or as a subparser).
    """

    return {
        'prog': 'CodeChecker cmd',
        'formatter_class': argparse.ArgumentDefaultsHelpFormatter,

        # Description is shown when the command's help is queried directly
        'description': "The command-line client is used to connect to a "
                       "running 'CodeChecker server' (either remote or "
                       "local) and quickly inspect analysis results, such as "
                       "runs, individual defect reports, compare analyses, "
                       "etc. Please see the invidual subcommands for further "
                       "details.",

        # Help is shown when the "parent" CodeChecker command lists the
        # individual subcommands.
        'help': "View analysis results on a running server from the "
                "command line.",
    }


def __add_common_arguments(parser,
                           needs_product_url=True,
                           has_matrix_output=False,
                           allow_html_output=False):
    """
    Add some common arguments, like server address and verbosity, to parser.
    """

    common_group = parser.add_argument_group('common arguments')

    if needs_product_url is None:
        # Explicitly not add anything, the command does not connect to a
        # server.
        pass
    elif needs_product_url:
        # Command connects to a product on a server.
        common_group.add_argument('--url',
                                  type=str,
                                  metavar='PRODUCT_URL',
                                  dest="product_url",
                                  default="localhost:8001/Default",
                                  required=False,
                                  help="The URL of the product which will be "
                                       "accessed by the client, in the "
                                       "format of"
                                       " '[http[s]://]host:port/Endpoint'.")
    else:
        # Command connects to a server directly.
        common_group.add_argument('--url',
                                  type=str,
                                  metavar='SERVER_URL',
                                  dest="server_url",
                                  default="localhost:8001",
                                  required=False,
                                  help="The URL of the server to access, "
                                       "in the format of"
                                       " '[http[s]://]host:port'.")

    if has_matrix_output:
        output_formats = ["plaintext"] + output_formatters.USER_FORMATS
        if allow_html_output:
            output_formats += ["html"]

        common_group.add_argument('-o', '--output',
                                  dest="output_format",
                                  required=False,
                                  # TODO: 'plaintext' only kept for legacy.
                                  default="plaintext",
                                  choices=output_formats,
                                  help="The output format to use in showing "
                                       "the data.")

        if allow_html_output:
            common_group.add_argument('-e', '--export-dir',
                                      dest="export_dir",
                                      default=argparse.SUPPRESS,
                                      help="Store the output in the given"
                                           "folder.")

            common_group.add_argument('-c', '--clean',
                                      dest="clean",
                                      required=False,
                                      action='store_true',
                                      default=argparse.SUPPRESS,
                                      help="Delete output results stored in"
                                           "the output directory. (By "
                                           "default, it would keep output "
                                           "files and overwrites only those "
                                           "that contain any reports).")

    logger.add_verbose_arguments(common_group)


def __add_filtering_arguments(parser, defaults=None, diff_mode=False):
    """
    Add some common filtering arguments to the given parser.
    """

    def init_default(dest):
        return defaults[dest] if defaults and dest in defaults \
            else argparse.SUPPRESS

    f_group = parser.add_argument_group('filter arguments')

    warn_diff_mode = ""
    if diff_mode:
        warn_diff_mode = " This can be used only if basename or newname is " \
                         "a run name (on the remote server)."

    f_group.add_argument('--report-hash',
                         nargs='*',
                         dest="report_hash",
                         metavar='REPORT_HASH',
                         default=init_default('report_hash'),
                         help="Filter results by report hashes.")

    f_group.add_argument('--review-status',
                         nargs='*',
                         dest="review_status",
                         metavar='REVIEW_STATUS',
                         default=init_default('review_status'),
                         help="Filter results by review statuses." +
                         warn_diff_mode)

    f_group.add_argument('--detection-status',
                         nargs='*',
                         dest="detection_status",
                         metavar='DETECTION_STATUS',
                         default=init_default('detection_status'),
                         help="Filter results by detection statuses." +
                         warn_diff_mode)

    f_group.add_argument('--severity',
                         nargs='*',
                         dest="severity",
                         metavar='SEVERITY',
                         default=init_default('severity'),
                         help="Filter results by severities.")

    f_group.add_argument('--tag',
                         nargs='*',
                         dest="tag",
                         metavar='TAG',
                         default=init_default('tag'),
                         help="Filter results by version tag names." +
                         warn_diff_mode)

    f_group.add_argument('--file',
                         nargs='*',
                         dest="file_path",
                         metavar='FILE_PATH',
                         default=init_default('file_path'),
                         help="Filter results by file path. "
                              "The file path can contain multiple * "
                              "quantifiers which matches any number of "
                              "characters (zero or more). So if you have "
                              "/a/x.cpp and /a/y.cpp then \"/a/*.cpp\" "
                              "selects both.")

    f_group.add_argument('--checker-name',
                         nargs='*',
                         dest="checker_name",
                         metavar='CHECKER_NAME',
                         default=init_default('checker_name'),
                         help="Filter results by checker names. "
                              "The checker name can contain multiple * "
                              "quantifiers which matches any number of "
                              "characters (zero or more). So for example "
                              "\"*DeadStores\" will matches "
                              "\"deadcode.DeadStores\"")

    f_group.add_argument('--checker-msg',
                         nargs='*',
                         dest="checker_msg",
                         metavar='CHECKER_MSG',
                         default=init_default('checker_msg'),
                         help="Filter results by checker messages."
                              "The checker message can contain multiple * "
                              "quantifiers which matches any number of "
                              "characters (zero or more).")

    f_group.add_argument('--component',
                         nargs='*',
                         dest="component",
                         metavar='COMPONENT',
                         default=argparse.SUPPRESS,
                         help="Filter results by source components." +
                         warn_diff_mode)

    f_group.add_argument('-s', '--suppressed',
                         default=argparse.SUPPRESS,
                         dest="suppressed",
                         action='store_true',
                         help="DEPRECATED. Use the '--filter' option to get "
                              "false positive (suppressed) results. Show only "
                              "suppressed results instead of only "
                              "unsuppressed ones.")

    f_group.add_argument('--filter',
                         type=str,
                         dest='filter',
                         default=argparse.SUPPRESS,
                         help="DEPRECATED. Filter results. Use separated "
                              "filter options to filter the results. The "
                              "filter string has the following format: "
                              "[<SEVERITIES>]:[<CHECKER_NAMES>]:"
                              "[<FILE_PATHS>]:[<DETECTION_STATUSES>]:"
                              "[<REVIEW_STATUSES>] where severites, "
                              "checker_names, file_paths, detection_statuses, "
                              "review_statuses should be a comma separated "
                              "list, e.g.: \"high,medium:unix,core:*.cpp,*.h:"
                              "new,unresolved:false_positive,intentional\"")


def __register_results(parser):
    """
    Add argparse subcommand parser for the "list analysis results" action.
    """

    parser.add_argument(type=str,
                        dest="name",
                        metavar='RUN_NAMES',
                        help="Names of the analysis runs to show result "
                             "summaries of. This has the following format: "
                             "<run_name_1>:<run_name_2>:<run_name_3> "
                             "where run names can contain * quantifiers which "
                             "matches any number of characters (zero or "
                             "more). So if you have run_1_a_name, "
                             "run_2_b_name, run_2_c_name, run_3_d_name then "
                             "\"run_2*:run_3_d_name\" selects the last three "
                             "runs. Use 'CodeChecker cmd runs' to get the "
                             "available runs.")

    __add_filtering_arguments(parser, DEFAULT_FILTER_VALUES)


def __register_diff(parser):
    """
    Add argparse subcommand parser for the "diff results" action.
    """

    parser.add_argument('-b', '--basename',
                        type=str,
                        dest="basename",
                        metavar='BASE_RUN',
                        required=True,
                        default=argparse.SUPPRESS,
                        help="The 'base' (left) side of the difference: this "
                             "analysis run is used as the initial state in "
                             "the comparison. The parameter can be a run name "
                             "(on the remote server) or a local report "
                             "directory (result of the analyze command). In "
                             "case of run name the the basename can contain * "
                             "quantifiers which matches any number of "
                             "characters (zero or more). So if you have "
                             "run-a-1, run-a-2 and run-b-1 "
                             "then \"run-a*\" selects the first two.")

    parser.add_argument('-n', '--newname',
                        type=str,
                        dest="newname",
                        metavar='NEW_RUN',
                        required=True,
                        default=argparse.SUPPRESS,
                        help="The 'new' (right) side of the difference: this "
                             "analysis run is compared to the -b/--basename "
                             "run. The parameter can be a run name "
                             "(on the remote server) or a local "
                             "report directory "
                             "(result of the analyze command). In case of run "
                             "name the newname can contain * quantifiers "
                             "which matches any number of characters "
                             "(zero or more). So if you have "
                             "run-a-1, run-a-2 and run-b-1 "
                             "then \"run-a*\" selects the first two.")

    __add_filtering_arguments(parser, DEFAULT_FILTER_VALUES, True)

    group = parser.add_argument_group("comparison modes")
    group = group.add_mutually_exclusive_group(required=True)

    group.add_argument('--new',
                       dest="new",
                       default=argparse.SUPPRESS,
                       action='store_true',
                       help="Show results that didn't exist in the 'base' "
                            "but appear in the 'new' run.")

    group.add_argument('--resolved',
                       dest="resolved",
                       default=argparse.SUPPRESS,
                       action='store_true',
                       help="Show results that existed in the 'base' but "
                            "disappeared from the 'new' run.")

    group.add_argument('--unresolved',
                       dest="unresolved",
                       default=argparse.SUPPRESS,
                       action='store_true',
                       help="Show results that appear in both the 'base' and "
                            "the 'new' run.")

    def __handle(args):
        """Custom handler for 'diff' so custom error messages can be
        printed without having to capture 'parser' in main."""

        output_dir = ['-e', '--export-dir']
        if args.output_format == 'html' and \
           not any(util.arg_match(output_dir, sys.argv[1:])):
            parser.error("argument --output html: not allowed without "
                         "argument --export-dir")

        cmd_line_client.handle_diff_results(args)

    parser.set_defaults(func=__handle)


def __register_sum(parser):
    """
    Add argparse subcommand parser for the "list result count by checker"
    action.
    """

    name_group = parser.add_mutually_exclusive_group(required=True)

    name_group.add_argument('-n', '--name',
                            type=str,
                            nargs='+',
                            dest="names",
                            metavar='RUN_NAME',
                            default=argparse.SUPPRESS,
                            help="Names of the analysis runs to show result "
                                 "count breakdown for. This has the following "
                                 "format: <run_name_1>:<run_name_2>:"
                                 "<run_name_3> where run names can be a "
                                 "Python regex expression. So if you have "
                                 "run_1_a_name, run_2_b_name, run_2_c_name, "
                                 "run_3_d_name then \"run_2*:run_3_d_name\""
                                 "selects the last three runs. Use "
                                 "'CodeChecker cmd runs' to get the available "
                                 "runs.")

    name_group.add_argument('-a', '--all',
                            dest="all_results",
                            action='store_true',
                            default=argparse.SUPPRESS,
                            help="Show breakdown for all analysis runs.")

    parser.add_argument('--disable-unique',
                        dest="disable_unique",
                        action='store_true',
                        default=argparse.SUPPRESS,
                        help="List all bugs even if these end up in the same "
                             "bug location, but reached through different "
                             "paths. By uniqueing the bugs a report will be "
                             "appeared only once even if it is found on "
                             "several paths.")

    __add_filtering_arguments(parser)


def __register_delete(parser):
    """
    Add argparse subcommand parser for the "delete runs" action.
    """

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument('-n', '--name',
                       type=str,
                       nargs='+',
                       dest="name",
                       metavar='RUN_NAME',
                       default=argparse.SUPPRESS,
                       help="Full name(s) of the analysis run or runs to "
                            "delete.")

    group.add_argument('--all-before-run',
                       type=str,
                       dest="all_before_run",
                       metavar='RUN_NAME',
                       default=argparse.SUPPRESS,
                       help="Delete all runs that were stored to the server "
                            "BEFORE the specified one.")

    group.add_argument('--all-after-run',
                       type=str,
                       dest="all_after_run",
                       metavar='RUN_NAME',
                       default=argparse.SUPPRESS,
                       help="Delete all runs that were stored to the server "
                            "AFTER the specified one.")

    group.add_argument('--all-after-time',
                       type=valid_time,
                       dest="all_after_time",
                       metavar='TIMESTAMP',
                       default=argparse.SUPPRESS,
                       help="Delete all analysis runs that were stored to the "
                            "server AFTER the given timestamp. The format of "
                            "TIMESTAMP is "
                            "'year:month:day:hour:minute:second' (the "
                            "\"time\" part can be omitted, in which case "
                            "midnight (00:00:00) is used).")

    group.add_argument('--all-before-time',
                       type=valid_time,
                       dest="all_before_time",
                       metavar='TIMESTAMP',
                       default=argparse.SUPPRESS,
                       help="Delete all analysis runs that were stored to the "
                            "server BEFORE the given timestamp. The format of "
                            "TIMESTAMP is "
                            "'year:month:day:hour:minute:second' (the "
                            "\"time\" part can be omitted, in which case "
                            "midnight (00:00:00) is used).")


def __register_suppress(parser):
    """
    Add argparse subcommand parser for the "suppress file management" action.
    """

    parser.add_argument(type=str,
                        dest="name",
                        metavar='RUN_NAME',
                        default=argparse.SUPPRESS,
                        help="Name of the analysis run to suppress or "
                             "unsuppress a report in.")

    parser.add_argument('-f', '--force',
                        dest="force",
                        action='store_true',
                        default=argparse.SUPPRESS,
                        help="Enable suppression of already suppressed "
                             "reports.")

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument('-i', '--import',
                       type=str,
                       dest="input",
                       metavar='SUPPRESS_FILE',
                       default=argparse.SUPPRESS,
                       help="Import suppression from the suppress file into "
                            "the database.")


def __register_products(parser):
    """
    Add argparse subcommand parser for the "product management" action.
    """

    def __register_add(parser):
        """
        Add argparse subcommand parser for the "add new product" action.
        """
        parser.add_argument("endpoint",
                            type=str,
                            metavar='ENDPOINT',
                            default=argparse.SUPPRESS,
                            help="The URL endpoint where clients can access "
                                 "the analysis results for this product.")

        parser.add_argument('-n', '--name',
                            type=str,
                            dest="display_name",
                            default=argparse.SUPPRESS,
                            required=False,
                            help="A custom display name for the product, "
                                 "which will be shown in the viewer. This "
                                 "is purely for decoration and user "
                                 "experience, program calls use the "
                                 "<ENDPOINT>.")

        parser.add_argument('--description',
                            type=str,
                            dest="description",
                            default=argparse.SUPPRESS,
                            required=False,
                            help="A custom textual description to be shown "
                                 "alongside the product.")

        dbmodes = parser.add_argument_group(
            "database arguments",
            "NOTE: These database arguments are relative to the server "
            "machine, as it is the server which will make the database "
            "connection.")

        dbmodes = dbmodes.add_mutually_exclusive_group(required=False)

        SQLITE_PRODUCT_ENDPOINT_DEFAULT_VAR = '<ENDPOINT>.sqlite'
        dbmodes.add_argument('--sqlite',
                             type=str,
                             dest="sqlite",
                             metavar='SQLITE_FILE',
                             default=SQLITE_PRODUCT_ENDPOINT_DEFAULT_VAR,
                             required=False,
                             help="Path of the SQLite database file to use. "
                                  "Not absolute paths will be relative to "
                                  "the server's <CONFIG_DIRECTORY>.")

        dbmodes.add_argument('--postgresql',
                             dest="postgresql",
                             action='store_true',
                             required=False,
                             default=argparse.SUPPRESS,
                             help="Specifies that a PostgreSQL database is "
                                  "to be used instead of SQLite. See the "
                                  "\"PostgreSQL arguments\" section on how "
                                  "to configure the database connection.")

        PGSQL_PRODUCT_ENDPOINT_DEFAULT_VAR = '<ENDPOINT>'
        pgsql = parser.add_argument_group(
            "PostgreSQL arguments",
            "Values of these arguments are ignored, unless '--postgresql' is "
            "specified! The database specified here must exist, and be "
            "connectible by the server.")

        # TODO: --dbSOMETHING arguments are kept to not break interface from
        # old command. Database using commands such as "CodeChecker store" no
        # longer supports these --- it would be ideal to break and remove args
        # with this style and only keep --db-SOMETHING.
        pgsql.add_argument('--dbaddress', '--db-host',
                           type=str,
                           dest="dbaddress",
                           default="localhost",
                           required=False,
                           help="Database server address.")

        pgsql.add_argument('--dbport', '--db-port',
                           type=int,
                           dest="dbport",
                           default=5432,
                           required=False,
                           help="Database server port.")

        pgsql.add_argument('--dbusername', '--db-username',
                           type=str,
                           dest="dbusername",
                           default=PGSQL_PRODUCT_ENDPOINT_DEFAULT_VAR,
                           required=False,
                           help="Username to use for connection.")

        pgsql.add_argument('--dbpassword', '--db-password',
                           type=str,
                           dest="dbpassword",
                           default="",
                           required=False,
                           help="Password to use for authenticating the "
                                "connection.")

        pgsql.add_argument('--dbname', '--db-name',
                           type=str,
                           dest="dbname",
                           default=PGSQL_PRODUCT_ENDPOINT_DEFAULT_VAR,
                           required=False,
                           help="Name of the database to use.")

        def __handle(args):
            """Custom handler for 'add' so custom error messages can be
            printed without having to capture 'parser' in main."""

            def arg_match(options):
                """Checks and selects the option string specified in 'options'
                that are present in the invocation argv."""
                matched_args = []
                for option in options:
                    if any([arg if option.startswith(arg) else None
                            for arg in sys.argv[1:]]):
                        matched_args.append(option)
                        continue

                return matched_args

            # See if there is a "PostgreSQL argument" specified in the
            # invocation without '--postgresql' being there. There is no way
            # to distinguish a default argument and a deliberately specified
            # argument without inspecting sys.argv.
            options = ['--dbaddress', '--dbport', '--dbusername', '--dbname',
                       '--db-host', '--db-port', '--db-username', '--db-name']
            psql_args_matching = arg_match(options)
            if any(psql_args_matching) and \
                    'postgresql' not in args:
                first_matching_arg = next(iter([match for match
                                                in psql_args_matching]))
                parser.error("argument {0}: not allowed without argument "
                             "--postgresql".format(first_matching_arg))
                # parser.error() terminates with return code 2.

            # Some arguments get a dynamic default value that depends on the
            # value of another argument.
            if args.sqlite == SQLITE_PRODUCT_ENDPOINT_DEFAULT_VAR:
                args.sqlite = args.endpoint + '.sqlite'

            if args.dbusername == PGSQL_PRODUCT_ENDPOINT_DEFAULT_VAR:
                args.dbusername = args.endpoint

            if args.dbname == PGSQL_PRODUCT_ENDPOINT_DEFAULT_VAR:
                args.dbname = args.endpoint

            if 'postgresql' not in args:
                # The --db-SOMETHING arguments are irrelevant if --postgresql
                # is not used.
                delattr(args, 'dbaddress')
                delattr(args, 'dbport')
                delattr(args, 'dbusername')
                delattr(args, 'dbpassword')
                delattr(args, 'dbname')
            else:
                # If --postgresql is given, --sqlite is useless.
                delattr(args, 'sqlite')

            # If everything is fine, do call the handler for the subcommand.
            product_client.handle_add_product(args)

        parser.set_defaults(func=__handle)

    def __register_del(parser):
        """
        Add argparse subcommand parser for the "delete product" action.
        """
        parser.add_argument("endpoint",
                            type=str,
                            metavar='ENDPOINT',
                            default=argparse.SUPPRESS,
                            help="The URL endpoint where clients can access "
                                 "the analysis results for the product.")

    subcommands = parser.add_subparsers(title='available actions')

    # Create handlers for individual subcommands.
    list_p = subcommands.add_parser(
        'list',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="List the name and basic information about products "
                    "added to the server.",
        help="List products available on the server.")
    list_p.set_defaults(func=product_client.handle_list_products)
    __add_common_arguments(list_p,
                           needs_product_url=False, has_matrix_output=True)

    add = subcommands.add_parser(
        'add',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Create a new product to be managed by the server by "
                    "providing the product's details and database connection.",
        help="Register a new product to the server.")
    __register_add(add)
    __add_common_arguments(add, needs_product_url=False)

    del_p = subcommands.add_parser(
        'del',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Removes the specified product from the list of products "
                    "managed by the server. NOTE: This only removes the "
                    "association and disconnects the server from the "
                    "database -- NO actual ANALYSIS DATA is REMOVED. "
                    "Configuration, such as access control, however, WILL BE "
                    "LOST!",
        help="Delete a product from the server's products.")
    __register_del(del_p)
    del_p.set_defaults(func=product_client.handle_del_product)
    __add_common_arguments(del_p, needs_product_url=False)


def __register_source_components(parser):
    """
    Add argparse subcommand parser for the "source component management"
    action.
    """

    def __register_add(parser):
        parser.add_argument("name",
                            type=str,
                            metavar='NAME',
                            default=argparse.SUPPRESS,
                            help="Unique name of the source component.")

        parser.add_argument('--description',
                            type=str,
                            dest="description",
                            default=argparse.SUPPRESS,
                            required=False,
                            help="A custom textual description to be shown "
                                 "alongside the source component.")

        parser.add_argument('-i', '--import',
                            type=str,
                            dest="component_file",
                            metavar='COMPONENT_FILE',
                            default=argparse.SUPPRESS,
                            required=True,
                            help="Path to the source component file which "
                                 "contains multiple file paths. Each file "
                                 "path start with a '+' (path should be "
                                 "filtered) or '-' (path should not be "
                                 "filtered) sign. E.g.: \n"
                                 "  +/a/b/x.cpp\n"
                                 "  -/a/b/\n"
                                 "Please see the User guide for more "
                                 "information.")

    def __register_del(parser):
        """
        Add argparse subcommand parser for the "del component" action.
        """
        parser.add_argument("name",
                            type=str,
                            metavar='NAME',
                            default=argparse.SUPPRESS,
                            help="Name of the source component name which "
                                 "will be removed.")

    subcommands = parser.add_subparsers(title='available actions')

    # Create handlers for individual subcommands.
    list_components = subcommands.add_parser(
        'list',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="List the name and basic information about source "
                    "component added to the server.",
        help="List source components available on the server.")
    list_components.set_defaults(
        func=source_component_client.handle_list_components)
    __add_common_arguments(list_components, has_matrix_output=True)

    add = subcommands.add_parser(
        'add',
        formatter_class=NewLineDefaultHelpFormatter,
        description="Creates a new source component or updates an existing "
                    "one.",
        help="Creates/updates a source component.")
    __register_add(add)
    add.set_defaults(func=source_component_client.handle_add_component)
    __add_common_arguments(add)

    del_c = subcommands.add_parser(
        'del',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Removes the specified source component.",
        help="Delete a source component from the server.")
    __register_del(del_c)
    del_c.set_defaults(func=source_component_client.handle_del_component)
    __add_common_arguments(del_c)


def __register_login(parser):
    """
    Add argparse subcommand parser for the "handle authentication" action.
    """

    parser.add_argument(type=str,
                        dest="username",
                        metavar='USERNAME',
                        nargs='?',
                        default=getpass.getuser(),
                        help="The username to authenticate with.")

    parser.add_argument('-d', '--deactivate', '--logout',
                        dest="logout",
                        action='store_true',
                        default=argparse.SUPPRESS,
                        help="Send a logout request to end your privileged "
                             "session.")


def __register_run_histories(parser):
    """
    Add argparse subcommand parser for the "list run histories by run name"
    action.
    """

    parser.add_argument('-n', '--name',
                        type=str,
                        nargs='*',
                        dest="names",
                        metavar='RUN_NAME',
                        default=argparse.SUPPRESS,
                        required=False,
                        help="Names of the analysis runs to show history for. "
                             "If this argument is not supplied it will show "
                             "the history for all runs. This has the "
                             "following format: \"<run_name_1> <run_name_2> "
                             "<run_name_3>\" where run names can be a Python"
                             "regex expression. So if you have run_1_a_name, "
                             "run_2_b_name, run_2_c_name, run_3_d_name "
                             "then \"run_2* run_3_d_name\" shows history for "
                             "the last three runs. Use 'CodeChecker cmd runs' "
                             "to get the available runs.")


def __register_token(parser):
    """
    Add argparse subcommand parser for the "handle token" action.
    """

    def __register_new(parser):
        parser.add_argument("--description",
                            type=str,
                            metavar='DESCRIPTION',
                            default=argparse.SUPPRESS,
                            required=False,
                            help="A custom textual description to be shown "
                                 "alongside the token.")

    def __register_del(parser):
        """
        Add argparse subcommand parser for the "del token" action.
        """
        parser.add_argument("token",
                            type=str,
                            metavar='TOKEN',
                            default=argparse.SUPPRESS,
                            help="Personal access token which will be "
                                 "deleted.")

    subcommands = parser.add_subparsers(title='available actions')

    # Create handlers for individual subcommands.
    list_tokens = subcommands.add_parser(
        'list',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="List the available personal access tokens.",
        help="List tokens available on the server.")
    list_tokens.set_defaults(
        func=token_client.handle_list_tokens)
    __add_common_arguments(list_tokens, has_matrix_output=True,
                           needs_product_url=False)

    new_t = subcommands.add_parser(
        'new',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Creating a new personal access token.",
        help="Creates a new personal access token.")
    __register_new(new_t)
    new_t.set_defaults(func=token_client.handle_add_token)
    __add_common_arguments(new_t, needs_product_url=False)

    del_t = subcommands.add_parser(
        'del',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Removes the specified access token.",
        help="Deletes a token from the server.")
    __register_del(del_t)
    del_t.set_defaults(func=token_client.handle_del_token)
    __add_common_arguments(del_t, needs_product_url=False)


def add_arguments_to_parser(parser):
    """
    Add the subcommand's arguments to the given argparse.ArgumentParser.
    """

    subcommands = parser.add_subparsers(title='available actions')

    # Create handlers for individual subcommands.
    runs = subcommands.add_parser(
        'runs',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="List the analysis runs available on the server.",
        help="List the available analysis runs.")
    runs.set_defaults(func=cmd_line_client.handle_list_runs)
    __add_common_arguments(runs, has_matrix_output=True)

    run_histories = subcommands.add_parser(
        'history',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Show run history for some analysis runs.",
        help="Show run history of multiple runs.")
    __register_run_histories(run_histories)
    run_histories.set_defaults(func=cmd_line_client.handle_list_run_histories)
    __add_common_arguments(run_histories, has_matrix_output=True)

    results = subcommands.add_parser(
        'results',
        formatter_class=util.RawDescriptionDefaultHelpFormatter,
        description="Show the individual analysis reports' summary.",
        help="List analysis result (finding) summary for a given run.",
        epilog='''Example scenario: List analysis results
------------------------------------------------
Get analysis results for a run:
    CodeChecker cmd results my_run

Get analysis results for multiple runs:
    CodeChecker cmd results "my_run1:my_run2"

Get analysis results by using regex:
    CodeChecker cmd results "my_run*"

Get analysis results for a run and filter the analysis results:
    CodeChecker cmd results my_run --severity critical high medium \\
        --file "/home/username/my_project/*"

    CodeChecker cmd results my_run --review-status confirmed unreviewed \\
        --component my_component_name''')
    __register_results(results)
    results.set_defaults(func=cmd_line_client.handle_list_results)
    __add_common_arguments(results, has_matrix_output=True)

    diff = subcommands.add_parser(
        'diff',
        formatter_class=util.RawDescriptionDefaultHelpFormatter,
        description="Compare two analysis runs to show the results that "
                    "differ between the two.",
        help="Compare two analysis runs and show the difference.",
        epilog='''Example scenario: Compare multiple analysis runs
------------------------------------------------
Compare two runs and show results that didn't exist in the 'run1' but appear in
the 'run2' run:
    CodeChecker cmd diff -b run1 -n run2 --new

Compare a remote run with a local report directory and show results that didn't
exist in the remote run 'run1' but appear in the local report directory:
    CodeChecker cmd diff -b run1 -n /my_report_dir --new

Compare two runs and show results that exist in both runs and filter results
by multiple severity values:
    CodeChecker cmd diff -b run1 -n run2 --unresolved --severity high medium'''
    )
    __register_diff(diff)
    __add_common_arguments(diff, has_matrix_output=True,
                           allow_html_output=True)

    sum_p = subcommands.add_parser(
        'sum',
        formatter_class=util.RawDescriptionDefaultHelpFormatter,
        description="Show checker statistics for some analysis runs.",
        help="Show statistics of checkers.",
        epilog='''Example scenario: Get checker statistics
------------------------------------------------
Get statistics for a run:
    CodeChecker cmd sum -n my_run

Get statistics for all runs filtered by multiple checker names:
    CodeChecker cmd sum --all --checker-name "core.*" "deadcode.*"

Get statistics for all runs and only for severity 'high':
    CodeChecker cmd sum --all --severity "high"''')
    __register_sum(sum_p)
    sum_p.set_defaults(func=cmd_line_client.handle_list_result_types)
    __add_common_arguments(sum_p, has_matrix_output=True)

    token = subcommands.add_parser(
        'token',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Access subcommands related to configuring personal "
                    "access tokens managed by a CodeChecker server. Please "
                    "see the individual subcommands for details.",
        help="Access subcommands related to configuring personal access "
             "tokens managed by a CodeChecker server.")
    __register_token(token)

    del_p = subcommands.add_parser(
        'del',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Remove analysis runs from the server based on some "
                    "criteria. NOTE! When a run is deleted, ALL associated "
                    "information is permanently lost!",
        help="Delete analysis runs.")
    __register_delete(del_p)
    del_p.set_defaults(func=cmd_line_client.handle_remove_run_results)
    __add_common_arguments(del_p)

    suppress = subcommands.add_parser(
        'suppress',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Imports suppressions from a suppress file to a "
                    "CodeChecker server.",
        help="Manage and import suppressions of a CodeChecker server.")
    __register_suppress(suppress)
    suppress.set_defaults(func=cmd_line_client.handle_suppress)
    __add_common_arguments(suppress)

    products = subcommands.add_parser(
        'products',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="CodeChecker organises its databases into products. "
                    "Each product has an individually configured database "
                    "which stores the analysis results. These subcommands "
                    "are used to manage the products configured by the "
                    "server. Please see the individual subcommands for "
                    "details.",
        epilog="Most of these commands require authentication and "
               "appropriate access rights. Please see 'CodeChecker cmd "
               "login' to authenticate.",
        help="Access subcommands related to configuring the products managed "
             "by a CodeChecker server.")
    __register_products(products)
    __add_common_arguments(products, needs_product_url=None)

    components = subcommands.add_parser(
        'components',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Source components are named collection of directories "
                    "specified as directory filter.",
        help="Access subcommands related to configuring the source components "
             "managed by a CodeChecker server.")
    __register_source_components(components)
    __add_common_arguments(components)

    login = subcommands.add_parser(
        'login',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Certain CodeChecker servers can require elevated "
                    "privileges to access analysis results. In such cases "
                    "it is mandatory to authenticate to the server. This "
                    "action is used to perform an authentication in the "
                    "command-line.",
        help="Authenticate into CodeChecker servers that require privileges.")
    __register_login(login)
    login.set_defaults(func=cmd_line_client.handle_login)
    __add_common_arguments(login, needs_product_url=False)

# 'cmd' does not have a main() method in itself, as individual subcommands are
# handled later on separately.
