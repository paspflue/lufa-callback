# LUFA Callback Plugin
An Ansible callback plugin that sends playbook execution data to the [LUFA](https://github.com/GISA-OSS/lufa) dashboard for monitoring and
visualization.

## Overview
This callback plugin records events during the execution of Ansible playbooks and sends them to a LUFA instance 
via HTTP requests. It tracks the execution of tasks and their results, providing detailed monitoring capabilities for 
AWX automation jobs in LUFA.

## Features
- Real-time task execution tracking
- Job statistics and result aggregation
- Secret detection and masking in extra_vars
- Support for multiple LUFA endpoints
- Automatic handling of task states (started, ok, changed, ...)
- Job artifacts collection

## Dependencies
- ansible (tested with 2.16)
- Python `requests` library (`pip install requests`)

## Installation
### Via Pod spec in AWX
1. Copy the file `lufa.py` to one kubernetes controlplane, where the AWX is running.
2. Create a configmap in your AWX-namespace with the file `lufa.py`:
``` bash
kubectl -n <awx-namespace> create configmap --from-file lufa.py lufa-callback
```
3. In AWX go to **Administration > Instance Groups > _default_**
4. The configmap can then be mounted as a volume in AWX by adding the following to your Pod spec:
``` yaml
spec:
    containers:
      - name: worker
        volumeMounts:
          - name: callbacks
            # This is the default path. It can be overwritten via:
            # https://docs.ansible.com/projects/ansible/latest/reference_appendices/config.html#default-callback-plugin-path
            mountPath: /usr/share/ansible/plugins/callback
    volumes:
        # The name is arbitrary, but must match the name in volumeMounts
      - name: callbacks
        projected:
            sources:
              # The configMap name must match the one from the kubectl-command.
              - configMap:
                    name: lufa-callback
                    items:
                      - key: lufa.py
                        path: lufa.py
              # More callback-plugins could be mounted here.
```

### In the Execution Environment
Alternatively the plugin file `lufa.py` can be copied in the folder /usr/share/ansible/plugins/callback of your execution environment.

## Configuration
The plugin can be configured via environment variables. Following options exist:
* [LUFA_ENDPOINT_URIS](#endpoint_uris-required)
* [LUFA_API_KEY](#api_key-required)
* [LUFA_REPLACE_SECRETS](#replace_secrets-optional)

> [!NOTE]
> In AWX, configuration should be done via **environment variables** under 
**Settings > Jobs settings > Extra Environment Variables**. The ansible.cfg configuration is only intended for testing and development purposes.

### endpoint_uris (required)
Comma-separated list of URIs where the LUFA instances are running.

- Environment: `LUFA_ENDPOINT_URIS`
- INI: `[lufa]` section, `endpoint_uris` key

Example: `https://lufa1.example.com,https://lufa2.example.com`

### api_key (required)
API key for authenticating with the LUFA instance.

- Environment: `LUFA_API_KEY`
- INI: `[lufa]` section, `api_key` key

### replace_secrets (optional)
Controls how secret values in extra_vars are handled. (See [secret detection](#secret-detection))

- Environment: `LUFA_REPLACE_SECRETS`
- INI: `[lufa]` section, `replace_secrets` key
- Type: boolean
- Default: `false`

**Behavior:**
- When `true`: Secret values are replaced with `[SECRET]`
- When `false`: Secret keys are completely removed from the data

## Secret Detection
The plugin automatically detects and handles sensitive information in Ansible `extra_vars`.
Any variables containing one of the following case-insensitive keywords are considered secrets:
- `password`
- `pass`
- `token`
- `key`
- `auth`
- `secret`
- `vault`
- `passphrase`
- `card`

**Example:**

If your extra_vars contain:
```json
{
  "db_password": "mysecret123",
  "api_token": "abc123xyz",
  "username": "admin",
  "database_host": "db.example.com"
}
```

With `replace_secrets=true`:
```json
{
  "db_password": "[SECRET]",
  "api_token": "[SECRET]",
  "username": "admin",
  "database_host": "db.example.com"
}
```

With `replace_secrets=false` (default):
```json
{
  "username": "admin",
  "database_host": "db.example.com"
}
```

## Required in extra vars
The following variables must be provided as Ansible extra variables (`--extra-vars` or `-e` ) for the plugin to
function properly:
- `tower_job_id` - AWX job ID (required, disables plugin if not present)
- `tower_job_template_id` - Job template ID (required)
- `tower_job_template_name` - Job template name (required)
- `tower_user_name` - Username who triggered the job
- `tower_schedule_id` - Schedule ID (if job is scheduled)
- `tower_schedule_name` - Schedule name (if job is scheduled)
- `tower_workflow_job_id` - Workflow job ID (if part of a workflow)
- `tower_workflow_job_name` - Workflow job name (if part of a workflow)

> [!NOTE]
> In AWX, these variables are provided automatically. For local testing with Ansible CLI, these variables 
must be passed explicitly using extra vars (`-e var=...`).

### Optional Extra Variables
- `lufa_compliance_interval` - Set to number of days a job needs to run on host be compliant (default: `0`)
- `lufa_template_infos` - Additional template information as JSON object

## How It Works
The plugin operates in the following workflow:
1. **Job Start** (`v2_playbook_on_play_start`): Sends job metadata including extra_vars (with secrets handled
according to configuration)
2. **Task Registration** (`v2_runner_on_start`): Registers new tasks with the dashboard
3. **Task Execution**: Reports task callbacks for each host with states:
   - `started` - Task execution has started
   - `ok` - Task completed successfully
   - `changed` - Task made changes
   - `failed` - Task failed
   - `ignored` - Task failed but ignored
   - `rescued` - Task failed but was rescued by rescue block
   - `skipped` - Task was skipped
   - `unreachable` - Host was unreachable
4. **Job Completion** (`v2_playbook_on_stats`): Sends final playbook statistics and job artifacts

## Related Projects
This plugin is part of the [LUFA](https://github.com/GISA-OSS/lufa) project, which provides a comprehensive
dashboard for Automation job monitoring and visualization.

## Testing
### Unit Tests
1. Install dependencies:
```bash
pip install -r requirements-dev.txt
```
2. Run tests:
```bash
cd tests/unit; PYTHONPATH=../..: pytest -v
```

## Disclaimer
This project provides a custom Ansible callback plugin and is not affiliated with, endorsed by, or supported by
Red Hat, Inc. The names are used strictly for descriptive purposes of compatibility.
- The AWX Project is a trademark of Red Hat, Inc., used with permission in accordance with the [AWX Trademark Guidelines](https://github.com/ansible/awx-logos/blob/master/TRADEMARKS.md).
- Ansible is a registered trademark of Red Hat, Inc.
