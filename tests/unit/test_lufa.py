from lufa import CallbackModule, hide_secret_vars, BAD_SECRET_WORDS


class TestGetAnsibleHost:
    def test_cmdb_name_is_returned(self):
        assert (
            CallbackModule().get_ansible_host({"cmdb": {"name": "myhost"}}) == "myhost"
        )

    def test_inventory_hostname_is_returned(self):
        assert (
            CallbackModule().get_ansible_host({"inventory_hostname": "myhost"})
            == "myhost"
        )

    def test_cmdb_name_is_prefered_over_inventory_hostname(self):
        assert (
            CallbackModule().get_ansible_host(
                {"cmdb": {"name": "correct_host"}, "inventory_hostname": "wrong_host"}
            )
            == "correct_host"
        )


class TestHideSecretVars:
    def test_empty_extra_vars_should_be_unchanged(self):
        assert hide_secret_vars({}) == {}

    def test_dictionary_returned_unchanged_without_bad_secret_words(self):
        orig = {"harmless": "earth"}
        assert hide_secret_vars({**orig}) == {**orig}

    def test_dictionary_key_password_is_removed(self):
        assert hide_secret_vars({"password": 42}) == {}

    def test_dictionary_key_secret_is_removed(self):
        assert hide_secret_vars({"secret": 42}) == {}

    def test_dictionary_key_card_is_removed(self):
        assert hide_secret_vars({"card": 42}) == {}

    def test_bad_secret_words_key_is_removed_while_good_word_is_not(self):
        assert hide_secret_vars({"harmless": "earth", "secret": 42}) == {
            "harmless": "earth"
        }

    def test_dictionary_key_password_is_replaced(self):
        assert hide_secret_vars({"password": 42}, True) == {"password": "[SECRET]"}

    def test_dictionary_key_secret_is_replaced(self):
        assert hide_secret_vars({"secret": 42}, True) == {"secret": "[SECRET]"}

    def test_dictionary_key_card_is_replaced(self):
        assert hide_secret_vars({"card": 42}, True) == {"card": "[SECRET]"}

    def test_bad_secret_words_key_is_replaced_while_good_word_is_not(self):
        assert hide_secret_vars({"harmless": "earth", "secret": 42}, True) == {
            "harmless": "earth",
            "secret": "[SECRET]",
        }

    def test_keys_that_share_pre_postfix_should_not_match(self):
        orig = {
            "primary_keyboard": "visible",
            "keyboard_layout": "see",
            "passenger_count": 42,
        }
        assert hide_secret_vars({**orig}, True) == {**orig}

    def test_keys_that_share_word_is_removed(self):
        assert (
            hide_secret_vars(
                {"ansible_hashi_vault_secret_id": 42, "ansible_hashi_vault_role_id": 43}
            )
            == {}
        )

    def test_keys_that_share_word_is_replaced(self):
        assert hide_secret_vars(
            {"ansible_hashi_vault_secret_id": 42, "ansible_hashi_vault_role_id": 43},
            True,
        ) == {
            "ansible_hashi_vault_secret_id": "[SECRET]",
            "ansible_hashi_vault_role_id": "[SECRET]",
        }

    def test_bad_words_with_underscore_is_removed(self):
        BAD_SECRET_WORDS.extend(["result_dump", "task_ansible_uuid", "ansible_uuid"])
        assert (
            hide_secret_vars(
                {"result_dump": 42, "task_ansible_uuid": 43, "ansible_uuid": 44}
            )
            == {}
        )

    def test_bad_words_with_underscore_is_replaced(self):
        BAD_SECRET_WORDS.extend(["result_dump", "task_ansible_uuid", "ansible_uuid"])
        assert hide_secret_vars(
            {"result_dump": 42, "task_ansible_uuid": 43, "ansible_uuid": 44}, True
        ) == {
            "result_dump": "[SECRET]",
            "task_ansible_uuid": "[SECRET]",
            "ansible_uuid": "[SECRET]",
        }
