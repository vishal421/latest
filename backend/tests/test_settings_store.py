from app.store import store


def setup_function():
    store.clear_all_for_tests()


def test_organization_profile_defaults_empty_then_persists():
    profile = store.get_organization_profile()
    assert profile["admin_name"] == ""

    updated = store.set_organization_profile("Vish", "vish@example.com", "Example Corp")
    assert updated["admin_name"] == "Vish"

    fetched_again = store.get_organization_profile()
    assert fetched_again["admin_email"] == "vish@example.com"
    assert fetched_again["organization_name"] == "Example Corp"
