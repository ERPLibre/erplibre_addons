import asyncio
import configparser
import os
import sys

# import git
# from colorama import Fore
import tempfile
import time
import uuid
from typing import Tuple

import aioshutil

from odoo import _, api, fields, models

# TODO use system instead
# Get root of ERPLibre
new_path = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
sys.path.append(new_path)

from script import lib_asyncio

lst_ignore_warning = [
    "have the same label:",
    "odoo.addons.code_generator.extractor_module_file: Ignore next error about"
    " ALTER TABLE DROP CONSTRAINT.",
]

lst_ignore_error = [
    "fetchmail_notify_error_to_sender",
    'odoo.sql_db: bad query: ALTER TABLE "db_backup" DROP CONSTRAINT'
    ' "db_backup_db_backup_name_unique"',
    'ERROR: constraint "db_backup_db_backup_name_unique" of relation'
    ' "db_backup" does not exist',
    'odoo.sql_db: bad query: ALTER TABLE "db_backup" DROP CONSTRAINT'
    ' "db_backup_db_backup_days_to_keep_positive"',
    'ERROR: constraint "db_backup_db_backup_days_to_keep_positive" of relation'
    ' "db_backup" does not exist',
    "odoo.addons.code_generator.extractor_module_file: Ignore next error about"
    " ALTER TABLE DROP CONSTRAINT.",
]


class DevopsCgTestCase(models.Model):
    _name = "devops.cg.test.case"
    _description = "devops_cg_test_case"

    name = fields.Char()

    coverage = fields.Boolean()

    install_path = fields.Char()

    keep_cache = fields.Boolean()

    module_generated = fields.Many2many(
        comodel_name="devops.cg.module", relation="devops_module_generated_rel"
    )

    module_init_ids = fields.Many2many(
        comodel_name="devops.cg.module",
        string="Module Init",
        relation="devops_module_init_ids_rel",
    )

    module_search_class = fields.Many2many(
        comodel_name="devops.cg.module",
        relation="devops_module_search_class_rel",
    )

    module_tested = fields.Many2many(
        comodel_name="devops.cg.module", relation="devops_module_tested_rel"
    )

    path_module_check = fields.Char()

    restore_db_image_name = fields.Char()

    run_in_sandbox = fields.Boolean()

    script_after_init_check = fields.Char()

    test_name = fields.Char()

    async def async_execute(
        self,
        config,
    ) -> Tuple[str, int]:
        # Template
        res, status = await self.test_exec(
            "./addons/TechnoLibre_odoo-code-generator-template",
            generated_module="code_generator_demo_mariadb_sql_example_1",
            tested_module="code_generator_template_demo_mariadb_sql_example_1",
            search_class_module="demo_mariadb_sql_example_1",
            lst_init_module_name=[
                "code_generator_portal",
                "demo_mariadb_sql_example_1",
            ],
            test_name="mariadb_test-template",
            run_in_sandbox=True,
            keep_cache=config.keep_cache,
            coverage=config.coverage,
        )

        return res, status

    async def test_exec(
        self,
        path_module_check: str,
        generated_module=None,
        generate_path=None,
        tested_module=None,
        search_class_module=None,
        script_after_init_check=None,
        lst_init_module_name=None,
        test_name=None,
        install_path=None,
        run_in_sandbox=False,
        restore_db_image_name="erplibre_base",
        keep_cache=False,
        coverage=False,
    ) -> Tuple[str, int]:
        test_result = ""
        test_status = 0
        new_destination_path = None
        if search_class_module:
            if install_path is not None:
                path_template_to_generate = os.path.join(
                    install_path, tested_module
                )
            elif generate_path:
                path_template_to_generate = os.path.join(
                    generate_path, tested_module
                )
            else:
                path_template_to_generate = os.path.join(
                    path_module_check, tested_module
                )
            if generate_path is not None:
                path_module_to_generate = os.path.join(
                    generate_path, search_class_module
                )
            else:
                path_module_to_generate = os.path.join(
                    path_module_check, search_class_module
                )
        else:
            path_template_to_generate = None
            path_module_to_generate = None

        use_test_path_generic = False
        destination_path = None
        temp_dir_name = None
        if run_in_sandbox:
            if keep_cache:
                temp_dir = tempfile.mkdtemp()
                temp_dir_name = temp_dir
            else:
                temp_dir = tempfile.TemporaryDirectory()
                temp_dir_name = temp_dir.name
            print(temp_dir_name)
            temp_dir_name = os.path.join(temp_dir_name, "workspace")
            os.mkdir(temp_dir_name)

            lst_path_to_add_config = []
            lst_path_to_remove_config = []
            if not os.path.exists(path_module_check):
                return (
                    f"Error var path_module_check '{path_module_check}' not"
                    " exist.",
                    -1,
                )

            copy_path_module_check = path_module_check
            path_module_check = os.path.normpath(
                os.path.join(temp_dir_name, path_module_check)
            )

            if generated_module and path_module_check.endswith(
                "/" + generated_module
            ):
                use_test_path_generic = True
                destination_path = path_module_check[
                    : -(len(generated_module) + 1)
                ]
                copy_path = copy_path_module_check[
                    : -(len(generated_module) + 1)
                ]
            elif search_class_module and path_module_check.endswith(
                "/" + search_class_module
            ):
                destination_path = path_module_check[
                    : -(len(search_class_module) + 1)
                ]
                copy_path = copy_path_module_check[
                    : -(len(search_class_module) + 1)
                ]
            else:
                destination_path = path_module_check
                copy_path = copy_path_module_check

            lst_path_to_add_config.append(destination_path)
            lst_path_to_remove_config.append(copy_path)

            ignore_tree = await aioshutil.ignore_patterns(".git", "setup")
            await aioshutil.copytree(
                copy_path, destination_path, ignore=ignore_tree
            )
            # destination_path_with_git = os.path.join(destination_path, ".git")
            # if os.path.exists(destination_path_with_git):
            #     await aioshutil.rmtree(destination_path_with_git)
            # destination_path_with_setup = os.path.join(destination_path, "setup")
            # if os.path.exists(destination_path_with_setup):
            #     await aioshutil.rmtree(destination_path_with_setup)

            if tested_module:
                lst_module_to_test = tested_module.split(",")
                for module_name in lst_module_to_test:
                    # Update path to change new emplacement
                    s_lst_path_tested_module = (
                        await lib_asyncio.run_command_get_output(
                            "find", "./addons/", "-name", module_name
                        )
                    )
                    if not s_lst_path_tested_module:
                        return (
                            f"Error cannot find module '{path_module_check}'"
                            " not exist.",
                            -1,
                        )
                    else:
                        lst_path_tested_module = (
                            s_lst_path_tested_module.strip().split("\n")
                        )
                        s_first_path = lst_path_tested_module[0]
                        parent_dir = os.path.dirname(s_first_path)
                        # Copy it
                        if copy_path != parent_dir:
                            os.path.basename(parent_dir)
                            new_destination_path = os.path.join(
                                os.path.dirname(destination_path),
                                os.path.basename(parent_dir),
                            )
                            ignore_tree = await aioshutil.ignore_patterns(
                                ".git", "setup"
                            )
                            await aioshutil.copytree(
                                parent_dir,
                                new_destination_path,
                                ignore=ignore_tree,
                            )
                            # destination_path_with_git = os.path.join(
                            #     new_destination_path, ".git"
                            # )
                            # if os.path.exists(destination_path_with_git):
                            #     await aioshutil.rmtree(destination_path_with_git)
                            lst_path_to_add_config.append(new_destination_path)
                            lst_path_to_remove_config.append(parent_dir)

                        new_s_first_path = os.path.normpath(
                            os.path.join(temp_dir_name, s_first_path)
                        )

                        s_lst_path_generated_module = (
                            await lib_asyncio.run_command_get_output(
                                "find",
                                "./addons/",
                                "-name",
                                generated_module,
                                cwd=temp_dir_name,
                            )
                        )
                        if s_lst_path_generated_module:
                            lst_path_generated_module = (
                                s_lst_path_generated_module.strip().split("\n")
                            )
                            s_first_path = os.path.normpath(
                                os.path.join(
                                    temp_dir_name,
                                    os.path.dirname(
                                        lst_path_generated_module[0]
                                    ),
                                )
                            )
                        else:
                            # TODO This is wrong... bug in template if reach this case
                            s_first_path = destination_path

                        hook_file = os.path.join(new_s_first_path, "hooks.py")
                        with open(hook_file) as hook:
                            hook_line = hook.read()
                            has_template = (
                                "template_dir = os.path.normpath" in hook_line
                            )

                            # Goal, update path_module_generate, maybe commented
                            # Goal, update template_dir, maybe not exist
                            # TODO need to refactor this and use AST and not string research

                            # try find nb space indentation
                            lst_f_key = [
                                "# path_module_generate = ",
                                "#path_module_generate = ",
                                "path_module_generate = ",
                            ]
                            nb_space_indentation = None
                            first_index = None
                            for f_key in lst_f_key:
                                if f_key in hook_line:
                                    first_index = hook_line.find(f_key)
                                    f_begin_index = (
                                        hook_line.rfind("\n", 0, first_index)
                                        + 1
                                    )
                                    nb_space_indentation = (
                                        first_index - f_begin_index
                                    )
                                    break
                            if nb_space_indentation is None:
                                return (
                                    f"Cannot find keys '{lst_f_key}' in"
                                    f" {hook_file}",
                                    -1,
                                )
                            end_string = "\n\n"
                            index_end_string = hook_line.find(
                                end_string, first_index
                            )

                            if has_template:
                                new_hook_line = (
                                    hook_line[: first_index + len(f_key)]
                                    + f'"{s_first_path}"\n'
                                    + f'{nb_space_indentation * " "}template_dir'
                                    f' = "{s_first_path}/" + MODULE_NAME\n\n'
                                    + hook_line[index_end_string:]
                                )
                            else:
                                new_hook_line = (
                                    hook_line[: first_index + len(f_key)]
                                    + f'"{s_first_path}"\n'
                                    + hook_line[index_end_string:]
                                )
                            new_hook_line = new_hook_line.replace(
                                "# path_module_generate = ",
                                "path_module_generate = ",
                            )
                            new_hook_line = new_hook_line.replace(
                                '# "path_sync_code": path_module_generate,',
                                '"path_sync_code": path_module_generate,',
                            )
                        with open(hook_file, "w") as hook:
                            hook.write(new_hook_line)

            # Format editing code before commit
            # await lib_asyncio.run_command_get_output(
            #     "./script/maintenance/format.sh", temp_dir_name
            # )

            # init repo with git
            for dir_to_git in lst_path_to_add_config:
                await lib_asyncio.run_command_get_output(
                    "git", "init", ".", cwd=dir_to_git
                )
                await lib_asyncio.run_command_get_output(
                    "git", "add", ".", cwd=dir_to_git
                )
                await lib_asyncio.run_command_get_output(
                    "git", "commit", "-am", "'first commit'", cwd=dir_to_git
                )

            new_config_path = os.path.join(temp_dir_name, "config.conf")
            self.update_config(
                "./config.conf",
                new_config_path,
                lst_path_to_add_config=lst_path_to_add_config,
                lst_path_to_remove_config=lst_path_to_remove_config,
                module_name=generated_module,
            )
        else:
            new_config_path = None

        if install_path is None:
            install_path = path_module_check
        elif run_in_sandbox:
            install_path = os.path.normpath(
                os.path.join(temp_dir_name, install_path)
            )

        # Check code, init module to install
        if lst_init_module_name:
            for module_name in lst_init_module_name:
                res, status = await self.run_command(
                    "./script/code_generator/check_git_change_code_generator.sh",
                    path_module_check,
                    module_name,
                    test_name=test_name,
                )
                test_result += res
                test_status += status

        # Check code, module to generate
        if tested_module:
            res, status = await self.run_command(
                "./script/code_generator/check_git_change_code_generator.sh",
                path_module_check,
                tested_module,
                test_name=test_name,
            )
            test_result += res
            test_status += status

        # Leave when detect anomaly in check before start
        if test_status:
            return test_result, test_status

        # Execute script before start
        if script_after_init_check and not test_status:
            res, status = await self.run_command(script_after_init_check)
            test_result += res
            test_status += status

        is_db_create = False
        unique_database_name = f"test_demo_{uuid.uuid4()}"[:63]
        if not test_status:
            # Create database
            res, status = await self.run_command(
                "./script/database/db_restore.py",
                "--database",
                unique_database_name,
                "--image",
                restore_db_image_name,
                test_name=test_name,
            )
            test_result += res
            test_status += status
            is_db_create = not status

        if not test_status and lst_init_module_name:
            # Install required module
            str_test = ",".join(lst_init_module_name)
            if coverage:
                script_name = (
                    "./script/addons/coverage_install_addons_dev.sh"
                    if tested_module
                    else "./script/addons/coverage_install_addons.sh"
                )
            else:
                script_name = (
                    "./script/addons/install_addons_dev.sh"
                    if tested_module
                    else "./script/addons/install_addons.sh"
                )
            if new_config_path:
                res, status = await self.run_command(
                    script_name,
                    unique_database_name,
                    str_test,
                    new_config_path,
                    test_name=test_name,
                )
            else:
                res, status = await self.run_command(
                    script_name,
                    unique_database_name,
                    str_test,
                    test_name=test_name,
                )
            test_result += res
            test_status += status

        if not test_status and search_class_module and generated_module:
            # Update template with class/model/inherit
            res, status = await self.run_command(
                "./script/code_generator/search_class_model.py",
                "--quiet",
                "-d",
                path_module_to_generate,
                "-t",
                path_template_to_generate,
                test_name=test_name,
            )
            test_result += res
            test_status += status

        # test_generated_path = (
        #     install_path if destination_path is None else new_destination_path
        # )
        test_generated_path = (
            destination_path if use_test_path_generic else install_path
        )
        # if destination_path is None:
        #     destination_path = install_path

        if not test_status and tested_module and generated_module:
            cmd = (
                "./script/code_generator/coverage_install_and_test_code_generator.sh"
                if coverage
                else "./script/code_generator/install_and_test_code_generator.sh"
            )
            # Finally, the test
            if new_config_path:
                res, status = await self.run_command(
                    cmd,
                    unique_database_name,
                    tested_module,
                    test_generated_path,
                    generated_module,
                    new_config_path,
                    test_name=test_name,
                )
            else:
                res, status = await self.run_command(
                    cmd,
                    unique_database_name,
                    tested_module,
                    install_path,
                    generated_module,
                    test_name=test_name,
                )
            test_result += res
            test_status += status

        if is_db_create:
            res, status = await self.run_command(
                "./.venv/bin/python3",
                "./odoo/odoo-bin",
                "db",
                "--drop",
                "--database",
                unique_database_name,
                test_name=test_name,
            )
            test_result += res
            test_status += status

        return test_result, test_status

    def update_config(
        self,
        origin_config,
        new_path_config,
        lst_path_to_add_config=None,
        lst_path_to_remove_config=None,
        module_name=None,
    ):
        config_parser = configparser.ConfigParser()
        config_parser.read(origin_config)
        str_path = config_parser["options"]["addons_path"].strip(",")
        lst_path = str_path.split(",")

        # Clean path from test
        if lst_path_to_remove_config:
            for remove_key in lst_path_to_remove_config:
                if remove_key.startswith("./"):
                    remove_key = remove_key[2:]
                if module_name and remove_key.endswith(module_name):
                    remove_key = remove_key[: -(len(module_name) + 1)]
                for s_path in lst_path:
                    if s_path.endswith(remove_key):
                        lst_path.remove(s_path)
                        break
        if lst_path_to_add_config:
            for add_path in lst_path_to_add_config:
                if module_name and add_path.endswith(module_name):
                    add_path = add_path[: -(len(module_name) + 1)]
                lst_path.insert(0, add_path)
        s_new_path = ",".join(lst_path)
        config_parser["options"]["addons_path"] = s_new_path
        with open(new_path_config, "w") as configfile:
            config_parser.write(configfile)

    async def run_command(self, *args, test_name=None):
        # Create subprocess
        start_time = time.time()
        cmd_str = " ".join(args)
        process = await asyncio.create_subprocess_exec(
            *args,
            # stdout must a pipe to be accessible as process.stdout
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # Wait for the subprocess to finish
        stdout, stderr = await process.communicate()
        end_time = time.time()
        diff_sec = end_time - start_time
        # Return stdout + stderr, returncode
        str_out = "\n" + stdout.decode().strip() + "\n" if stdout else ""
        str_err = "\n" + stderr.decode().strip() + "\n" if stderr else ""
        status_str = "FAIL" if process.returncode else "PASS"
        if test_name:
            str_output_init = (
                f"\n\n{status_str} [{test_name}] [{diff_sec:.3f}s] Execute"
                f' "{cmd_str}"\n\n'
            )
        else:
            str_output_init = (
                f'\n\n{status_str} [{diff_sec:.3f}s] Execute "{cmd_str}"\n\n'
            )
        all_output = str_out + str_err
        print(str_output_init)
        if process.returncode:
            lst_error = []
            lst_warning = []
            self.extract_result(
                (all_output, process.returncode),
                test_name,
                lst_error,
                lst_warning,
            )
            for error in lst_error:
                print(f"\t{error}")
            for warning in lst_warning:
                print(f"\t{warning}")
        return str_output_init + all_output, process.returncode

    def extract_result(self, result, test_name, lst_error, lst_warning):
        lst_log = result[0].split("\n")
        for log_line in lst_log:
            is_ignore_error = False
            if "error" in log_line.lower():
                # Remove ignore error
                for ignore_error in lst_ignore_error:
                    if ignore_error in log_line:
                        is_ignore_error = True
                        break
                if not is_ignore_error:
                    lst_error.append(log_line)

            is_ignore_warning = False
            if "warning" in log_line.lower():
                # Remove ignore warning
                for ignore_warning in lst_ignore_warning:
                    if ignore_warning in log_line:
                        is_ignore_warning = True
                        break
                if not is_ignore_warning:
                    lst_warning.append(log_line)
        if result[1]:
            lst_error.append(f"Return status error for test {test_name}")
