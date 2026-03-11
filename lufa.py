import json
from typing import cast, Protocol, Callable, TypedDict

from ansible.playbook.task import Task
from ansible.playbook.play import Play
from ansible.playbook import Playbook
from ansible.plugins.callback import CallbackBase
from ansible.utils.fqcn import add_internal_fqcns
from ansible.vars.manager import VariableManager
from ansible.inventory.data import InventoryData, Host
import requests


DOCUMENTATION = """
    callback: lufa
    callback_type: notification
    short_description: Sends summary information to LUFA
    description:
      - This callback forwards summary information via POST requests to LUFA
    options:
      endpoint_uris:
        required: True
        description: URIs of the HTTP endpoint
        env:
          - name: LUFA_ENDPOINT_URIS
        ini:
          - section: lufa
            key: endpoint_uris
        type: str
      api_key:
        required: True
        description: The api key to publish data
        env:
          - name: LUFA_API_KEY
        ini:
          - section: lufa
            key: api_key
        type: str
      replace_secrets:
        description:
          - Replaces secret values with '[Secret]' if enabled.
          - If disabled, secret keys are removed
        env:
          - name: LUFA_REPLACE_SECRETS
        ini:
          - section: lufa
            key: replace_secrets
        type: bool
        default: False
"""
DEBUG = False


class MockRequest:
    def __init__(self, file):
        self.file = open(file, "a")

    def post(self, url: str, json: dict, headers: dict[str, str]) -> None:
        print(f"POST: {url} {hide_secret_vars(json, True)}", file=self.file)

    def patch(self, url: str, json: dict, headers: dict[str, str]) -> None:
        print(f"PATCH: {url} {hide_secret_vars(json, True)}", file=self.file)

    def put(self, url: str, json: dict, headers: dict[str, str]) -> None:
        print(f"PUT: {url} {hide_secret_vars(json, True)}", file=self.file)


class AnsibleResult(Protocol):
    _task: Task
    _host: Host
    _result: object
    _rescue: bool

    def is_changed(self) -> bool: ...


class HostStats(TypedDict):
    ok: int
    failures: int
    unreachable: int
    changed: int
    skipped: int
    rescued: int
    ignored: int


class AnsibleStats(Protocol):
    custom: dict
    processed: dict

    def summarize(self, hostname: str) -> HostStats: ...


BAD_SECRET_WORDS = [
    "password",
    "pass",
    "token",
    "key",
    "auth",
    "secret",
    "vault",
    "passphrase",
    "card",
]


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_NAME = "lufa"
    CALLBACK_NEEDS_WHITELIST = False

    _play: Play
    vm: VariableManager

    def __init__(self) -> None:
        self.endpoint_uris: list[str]
        self.api_key: str
        self.replace_secrets = False

        self._last_task_banner = None
        self._last_task_name: str | None = None
        self._play = cast(Play, None)
        self.vm = cast(VariableManager, None)

        self.playbook_path: str

        self.submitted_tasks: set[str] = (
            set()
        )  # Tasks that are submitted to the Dashboard

        # Not in AWX -> dont send data
        self.in_awx = True  # Will be false, if no tower_job_id is set

        super(CallbackModule, self).__init__()

    def set_options(self, task_keys=None, var_options=None, direct=None) -> None:
        super(CallbackModule, self).set_options(
            task_keys=task_keys, var_options=var_options, direct=direct
        )

        self.endpoint_uris = [
            item.strip() for item in self.get_option("endpoint_uris").split(",")
        ]
        self.api_key = self.get_option("api_key")
        self.replace_secrets = self.get_option("replace_secrets")
        if len(self.endpoint_uris) == 1 and self.endpoint_uris[0] == "out.txt":
            BAD_SECRET_WORDS.extend(
                ["result_dump", "task_ansible_uuid", "ansible_uuid"]
            )
            mock = MockRequest("out.txt")
            requests.post = cast(Callable, mock.post)
            requests.patch = cast(Callable, mock.patch)
            requests.put = cast(Callable, mock.put)

    def send_data(self, url: str, data, http_send: Callable) -> None:
        if not self.in_awx:
            return

        headers = {"Authorization": f"token {self.api_key}"}

        for uri in self.endpoint_uris:
            http_send(uri + url, json=data, headers=headers)

    def _set_task_name(self, task: Task) -> None:
        if getattr(self._play, "strategy", "None") in add_internal_fqcns(
            ("free", "host_pinned")
        ):
            # Explicitly set to None for strategy free/host_pinned to account for any cached
            # task title from a previous non-free play
            self._last_task_name = None
        else:
            self._last_task_name = cast(str, task.get_name()).strip()

    def get_ansible_host(self, host_vars: dict) -> str:
        """Returns name of host from host_vars.

        If available, the cmdb["name"] is used.
        If not, the inventory_hostname is used.
        """

        ansible_host = cast(str, host_vars.get("cmdb", {}).get("name"))
        if ansible_host is None:
            ansible_host = cast(str, host_vars.get("inventory_hostname"))

        return ansible_host

    def v2_runner_on_failed(self, result: AnsibleResult, ignore_errors=False) -> None:
        if DEBUG:
            self._display.display("v2_runner_on_failed")

        state = "failed"
        if result._task.ignore_errors:
            state = "ignored"

        task = result._task
        if hasattr(task, "_parent") and task._parent:
            parent = task._parent
            if hasattr(parent, "rescue") and parent.rescue:
                state = "rescued"

        data_task_callback = {
            "task_ansible_uuid": result._task._uuid,
            "ansible_host": self.get_ansible_host(result._host.get_vars()),
            "module": result._task.action,
            "state": state,
            "result_dump": json.dumps(result._result),
        }

        self.send_data("/task_callbacks", data_task_callback, requests.post)

    def v2_runner_on_ok(self, result: AnsibleResult) -> None:
        if DEBUG:
            self._display.display("v2_runner_on_ok")

        if result.is_changed():
            state = "changed"
        else:
            state = "ok"

        data_task_callback = {
            "task_ansible_uuid": result._task._uuid,
            "ansible_host": self.get_ansible_host(result._host.get_vars()),
            "module": result._task.action,
            "state": state,
            "result_dump": json.dumps(result._result),
        }

        self.send_data("/task_callbacks", data_task_callback, requests.post)

    def v2_runner_on_skipped(self, result: AnsibleResult) -> None:
        if DEBUG:
            self._display.display("v2_runner_on_skipped")

        data_task_callback = {
            "task_ansible_uuid": result._task._uuid,
            "ansible_host": self.get_ansible_host(result._host.get_vars()),
            "module": result._task.action,
            "state": "skipped",
            "result_dump": json.dumps(result._result),
        }

        self.send_data("/task_callbacks", data_task_callback, requests.post)

    def v2_runner_on_unreachable(self, result: AnsibleResult) -> None:
        if DEBUG:
            self._display.display("v2_runner_on_skipped")

        data_task_callback = {
            "task_ansible_uuid": result._task._uuid,
            "ansible_host": self.get_ansible_host(result._host.get_vars()),
            "module": result._task.action,
            "state": "unreachable",
            "result_dump": json.dumps(result._result),
        }

        self.send_data("/task_callbacks", data_task_callback, requests.post)

    def v2_playbook_on_task_start(self, task: Task, is_conditional: bool) -> None:
        self._set_task_name(task)

    def v2_playbook_on_cleanup_task_start(self, task: Task) -> None:
        self._set_task_name(task)

    def v2_playbook_on_handler_task_start(self, task: Task) -> None:
        self._set_task_name(task)

    def v2_runner_on_start(self, host, task: Task) -> None:
        if DEBUG:
            self._display.display("v2_runner_on_start")

        # Submitting Task to Dashboard
        if task._uuid not in self.submitted_tasks:
            data_task = {
                "ansible_uuid": task._uuid,
                "tower_job_id": self.vm.extra_vars.get("tower_job_id"),
                "task_name": self._last_task_name,
            }

            self.send_data("/tasks", data_task, requests.post)

            self.submitted_tasks.add(task._uuid)

        # Sending Callback
        data_task_callback = {
            "task_ansible_uuid": task._uuid,
            "ansible_host": self.get_ansible_host(host.get_vars()),
            "module": task.action,
            "state": "started",
            "result_dump": json.dumps(dict()),
        }

        self.send_data("/task_callbacks", data_task_callback, requests.post)

    def v2_playbook_on_play_start(self, play: Play) -> None:
        self.vm = cast(VariableManager, play.get_variable_manager())

        # Magic Vars contain Limit and Tags
        # The "None" values are defaults as taken from vars/manager.py Code
        magic_vars = self.vm._get_magic_variables(None, None, None, None, None)

        compliance_interval = self.vm.extra_vars.get("lufa_compliance_interval")
        if compliance_interval is None:
            compliance_interval = 0

        extra_vars = hide_secret_vars(self.vm.extra_vars, self.replace_secrets)

        data = {
            "tower_job_id": self.vm.extra_vars.get("tower_job_id"),
            "tower_job_template_id": self.vm.extra_vars.get("tower_job_template_id"),
            "tower_job_template_name": self.vm.extra_vars.get(
                "tower_job_template_name"
            ),
            "ansible_limit": magic_vars.get("ansible_limit"),
            "tower_user_name": self.vm.extra_vars.get("tower_user_name"),
            "awx_tags": json.dumps(magic_vars.get("ansible_run_tags")),
            "extra_vars": json.dumps(extra_vars),
            "artifacts": "{}",  # will be filled after job ends
            "tower_schedule_id": self.vm.extra_vars.get("tower_schedule_id"),
            "tower_schedule_name": self.vm.extra_vars.get("tower_schedule_name"),
            "tower_workflow_job_id": self.vm.extra_vars.get("tower_workflow_job_id"),
            "tower_workflow_job_name": self.vm.extra_vars.get(
                "tower_workflow_job_name"
            ),
            "compliance_interval": compliance_interval,
            "template_infos": json.dumps(self.vm.extra_vars.get("lufa_template_infos")),
            "playbook_path": self.playbook_path,
        }

        if data["tower_job_id"] is None:
            self.in_awx = False

        self.send_data("/jobs", data, requests.post)

    def v2_on_file_diff(self, result: AnsibleResult) -> None:
        pass

    def v2_runner_item_on_ok(self, result: AnsibleResult) -> None:
        pass

    def v2_runner_item_on_failed(self, result: AnsibleResult) -> None:
        pass

    def v2_runner_item_on_skipped(self, result: AnsibleResult) -> None:
        pass

    def v2_playbook_on_include(self, included_file) -> None:
        pass

    def v2_playbook_on_stats(self, stats: AnsibleStats) -> None:
        if DEBUG:
            self._display.display("v2_playbook_on_stats")

        # submit ending of job
        tower_job_id = self.vm.extra_vars.get("tower_job_id")
        data = {"event": "finished"}

        # add job artefacts like awx
        if hasattr(stats, "custom") and "_run" in stats.custom:
            data["artifacts"] = json.dumps(stats.custom["_run"])

        self.send_data("/jobs/" + str(tower_job_id), data, requests.patch)

        # submit stats
        data_stats = {
            "tower_job_id": self.vm.extra_vars.get("tower_job_id"),
            "stats": [],
        }

        hostnames = sorted(stats.processed.keys())
        for hostname in hostnames:
            host = cast(InventoryData, self.vm._inventory).get_host(
                hostname
            )  # get host object from hostname
            ansible_host = self.get_ansible_host(self.vm.get_vars(host=host))
            host_stats = stats.summarize(hostname)

            data_stats["stats"] += [
                {
                    "ansible_host": ansible_host,
                    "ok": host_stats["ok"],
                    "failed": host_stats[
                        "failures"
                    ],  # renamed to fit labeling of base plugin output
                    "unreachable": host_stats["unreachable"],
                    "changed": host_stats["changed"],
                    "skipped": host_stats["skipped"],
                    "rescued": host_stats["rescued"],
                    "ignored": host_stats["ignored"],
                }
            ]

        self.send_data("/stats", data_stats, requests.put)

    def v2_playbook_on_start(self, playbook: Playbook) -> None:
        self.playbook_path = cast(str, playbook._file_name)
        pass

    def v2_runner_retry(self, result: AnsibleResult) -> None:
        pass

    def v2_runner_on_async_poll(self, result: AnsibleResult) -> None:
        pass

    def v2_runner_on_async_ok(self, result: AnsibleResult) -> None:
        pass

    def v2_runner_on_async_failed(self, result: AnsibleResult) -> None:
        pass

    def v2_playbook_on_notify(self, handler, host: str) -> None:
        pass


def hide_secret_vars(extra_vars: dict, replace_secrets: bool = False) -> dict:
    """Delete sensitive data in extra_vars."""
    copy = dict(extra_vars)

    for key in extra_vars.keys():
        for keyword in BAD_SECRET_WORDS:
            if keyword in [word.lower() for word in key.split("_")] or keyword == key:
                if replace_secrets:
                    copy[key] = "[SECRET]"
                else:
                    del copy[key]
                break

    return copy
