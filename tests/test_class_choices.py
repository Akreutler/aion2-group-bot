"""/profile add validates the fields Discord can constrain. Run: pytest"""

from bot.cogs.profiles import Profile


def option(display_name):
    """One option of /profile add, by the name Discord shows."""
    command = next(c for c in Profile.__cog_app_commands__ if c.name == "add")
    return next(
        param
        for param in command._params.values()
        if param.display_name == display_name
    )


def test_role_stays_a_closed_list():
    assert [c.value for c in option("role").choices] == ["tank", "heal", "dps"]


def test_character_name_stays_free_text():
    assert not option("name").choices


def test_server_uses_autocomplete_instead_of_free_form_choices():
    server = option("server")
    assert not server.choices
    assert server.autocomplete is not None


def test_class_is_not_user_supplied_anymore():
    command = next(c for c in Profile.__cog_app_commands__ if c.name == "add")
    assert "class" not in {p.display_name for p in command._params.values()}
