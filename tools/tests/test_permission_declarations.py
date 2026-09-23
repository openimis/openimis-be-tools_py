"""
Garde-fous sur la declaration des droits de tools.

Meme structure que `claim` et `product` : `DJANGO_PERMS` par entite puis par action,
`_PERM_CFG` qui relie les cles de config, et `Extract.get_rights` comme point d'acces.

La difference de `tools`, et la raison d'etre de la moitie de ce fichier : ses onze
cles de config ne portent pas un identifiant mais une **pile** de plusieurs, evaluee en
OU par `has_perms`. La pile date du commit initial et reproduit le catalogue de l'IMIS
historique. Ce qui est verrouille ici :

  * la valeur exacte de chaque pile, ordre compris - c'est ce qui rend visible en revue
    toute conversion qui "nettoierait" un identifiant et retirerait du meme geste
    l'acces aux roles qui ne portent que celui-la ;
  * la liste des actions volontairement absentes de `_PERM_CFG` : les alternates
    empiles ne sont pas controlables separement aujourd'hui, et ajouter une action sans
    y penser doit faire echouer ce test ;
  * le fait que `configured()` renvoie None sur ces alternates, pour que l'appelant
    echoue ferme plutot que de recevoir la pile entiere en croyant tenir le seul droit
    d'ecriture.

Ce que ce fichier **ne** verrouille **pas**, faute de decision : la separation
lecture/ecriture des registres. `views.py` garde le `GET download_*` et le
`POST upload_*` avec la meme cle ; les actions `query` et `write` sont declarees
separement mais empilees dans la meme cle, donc la separation est nommee, pas faite.
"""

import json
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from tools.apps import (
    DJANGO_PERMS,
    ToolsConfig,
    _PERM_CFG,
    configured_perms,
    django_perms,
    perms,
)
from tools.models import Extract

# Les piles telles que deployees, ordre compris. En changer une est incompatible avec
# les roles existants : il faut mettre ce test a jour *et* accorder le nouveau droit.
EXPECTED_RIGHTS = {
    "registers_perms": ["131000", "131100"],
    "registers_diagnoses_perms": ["131000", "131002", "131001"],
    "registers_health_facilities_perms": ["131000", "131004", "131003"],
    "registers_locations_perms": ["131000", "131006", "131005"],
    "registers_items_perms": ["131000", "131008", "131007"],
    "registers_services_perms": ["131000", "131010", "131009"],
    "extracts_master_data_perms": ["131101"],
    "extracts_officer_feedbacks_perms": ["131106"],
    "extracts_officer_renewals_perms": ["131105"],
    "extracts_phone_extract_perms": ["131102", "131103"],
    "extracts_upload_claims_perms": ["131104"],
}

# Ce que `permissions_map.json` catalogue pour tools. Un seul identifiant par cle :
# `generate_permissions_map.py` ecrase la valeur a chaque tour de boucle, donc c'est le
# **dernier** de la pile qui sort. Les autres ne sont pas morts, ils sont
# inexprimables par une carte a un identifiant par cle.
CATALOGUED = {
    "tools.registers": "131100",
    "tools.registers_diagnoses": "131001",
    "tools.registers_health_facilities": "131003",
    "tools.registers_locations": "131005",
    "tools.registers_items": "131007",
    "tools.registers_services": "131009",
    "tools.extracts_master_data": "131101",
    "tools.extracts_officer_feedbacks": "131106",
    "tools.extracts_officer_renewals": "131105",
    "tools.extracts_phone_extract": "131103",
    "tools.extracts_upload_claims": "131104",
}

# Identifiants empiles qu'aucune entree de la carte ne nomme. Repris de
# `core.tests.test_permission_map_consistency.KNOWN_UNCATALOGUED`, epingle ici pour que
# la liste ne grossisse pas en silence.
UNCATALOGUED = {"131000", "131002", "131004", "131006", "131008", "131010", "131102"}

# Actions declarees sans cle de config a elles : les maillons empiles d'une pile dont
# la cle est portee par l'action principale. Aucune n'est controlable separement
# aujourd'hui.
STACKED_ALTERNATES = {
    ("registers", "any"),
    ("registersDiagnoses", "write"),
    ("registersHealthFacilities", "write"),
    ("registersLocations", "write"),
    ("registersItems", "write"),
    ("registersServices", "write"),
    ("phoneExtract", "queryAlt"),
}


class ToolsPermissionDeclarationTestCase(TestCase):
    def test_right_ids_unchanged(self):
        """La conversion ne doit rien retirer d'une pile - pas meme l'ordre."""
        self.assertEqual(
            {key: getattr(ToolsConfig, key) for key in EXPECTED_RIGHTS}, EXPECTED_RIGHTS
        )

    def test_perm_cfg_points_at_declared_actions_only(self):
        declared = {
            (entity, action)
            for entity, actions in DJANGO_PERMS.items()
            for action in actions
        }
        self.assertEqual(set(_PERM_CFG.values()) - declared, set())

    def test_actions_without_a_config_key_are_only_the_stacked_alternates(self):
        declared = {
            (entity, action)
            for entity, actions in DJANGO_PERMS.items()
            for action in actions
        }
        self.assertEqual(declared - set(_PERM_CFG.values()), STACKED_ALTERNATES)

    def test_perm_cfg_matches_config_attributes(self):
        """`__load_config` ignores the keys with no class attribute."""
        missing = [key for key in _PERM_CFG if not hasattr(ToolsConfig, key)]
        self.assertEqual(missing, [])

    def test_no_right_list_is_empty(self):
        """`has_perms([])` renvoie True : une pile vide accorderait a tout le monde."""
        empty = [key for key in _PERM_CFG if not getattr(ToolsConfig, key)]
        self.assertEqual(empty, [])

    def test_every_declared_id_is_used_by_a_config_key(self):
        """Aucun identifiant declare ne doit rester hors des piles posees."""
        declared_ids = {
            str(right_id)
            for actions in DJANGO_PERMS.values()
            for _, right_id in actions.values()
        }
        used = {rid for key in _PERM_CFG for rid in getattr(ToolsConfig, key)}
        self.assertEqual(declared_ids, used)

    def test_catalogued_ids_are_the_last_of_their_stack(self):
        """
        Chaque cle catalogue l'identifiant de son action principale, et c'est aussi le
        dernier de la pile - ce que le generateur de la carte produit mecaniquement.
        """
        for key, expected in EXPECTED_RIGHTS.items():
            entity, action = _PERM_CFG[key]
            with self.subTest(key=key):
                self.assertEqual(perms(entity, action), [expected[-1]])

    def test_catalogue_matches_permissions_map(self):
        """
        Le catalogue de l'assemblage, pas celui du paquet : les modules sont installes
        depuis un autre arbre, donc on le resout depuis BASE_DIR.
        """
        path = Path(settings.BASE_DIR) / "permissions_map.json"
        if not path.exists():  # pragma: no cover - assemblage sans carte
            self.skipTest(f"{path} absent")
        catalogue = json.loads(path.read_text(encoding="utf-8"))
        actual = {
            key: str(value)
            for key, value in catalogue.items()
            if key.startswith("tools.")
        }
        self.assertEqual(actual, CATALOGUED)

    def test_uncatalogued_ids_are_exactly_the_stacked_alternates(self):
        catalogued = set(CATALOGUED.values())
        declared_ids = {
            str(right_id)
            for actions in DJANGO_PERMS.values()
            for _, right_id in actions.values()
        }
        self.assertEqual(declared_ids - catalogued, UNCATALOGUED)

    def test_stacked_alternates_carry_the_uncatalogued_ids(self):
        self.assertEqual(
            {perms(entity, action)[0] for entity, action in STACKED_ALTERNATES},
            UNCATALOGUED,
        )

    def test_no_right_id_is_shared(self):
        """
        Contrairement a claim ou insuree, tools n'a aucun alias volontaire : chaque
        identifiant est declare une fois et une seule. 131000 en particulier est
        factorise sur l'entite `registers` plutot que repete sur les cinq registres.
        """
        seen = {}
        for entity, actions in DJANGO_PERMS.items():
            for action, (_, right_id) in actions.items():
                seen.setdefault(right_id, []).append(f"{entity}.{action}")
        shared = {rid: who for rid, who in seen.items() if len(who) > 1}
        self.assertEqual(shared, {})

    def test_django_permission_names_are_unique(self):
        seen = {}
        for entity, actions in DJANGO_PERMS.items():
            for action, (name, _) in actions.items():
                seen.setdefault(name, []).append(f"{entity}.{action}")
        shared = {name: who for name, who in seen.items() if len(who) > 1}
        self.assertEqual(shared, {})

    def test_unknown_entity_or_action_raises(self):
        with self.assertRaises(KeyError):
            perms("nosuchentity", "query")
        with self.assertRaises(KeyError):
            perms("registersItems", "nosuchaction")
        with self.assertRaises(KeyError):
            django_perms("registersItems", "nosuchaction")

    # --- the access point through the model -------------------------------
    def test_extract_exposes_the_phone_extract_read(self):
        self.assertEqual(
            Extract.get_rights("query"), configured_perms("phoneExtract", "query")
        )
        self.assertEqual(Extract.get_rights("query"), EXPECTED_RIGHTS["extracts_phone_extract_perms"])

    def test_stacked_alternate_has_no_configured_value(self):
        """None means "no rule": the caller must fail closed."""
        self.assertIsNone(Extract.get_rights("queryAlt"))
        self.assertIsNone(Extract.get_rights("nosuchaction"))
        for entity, action in STACKED_ALTERNATES:
            with self.subTest(entity=entity, action=action):
                self.assertIsNone(configured_perms(entity, action))

    def test_model_reads_the_configured_value_not_the_declared_default(self):
        """
        ModuleConfiguration may override a right; the check must read the configured
        value, where `perms()` returns the declared default.
        """
        original = ToolsConfig.extracts_phone_extract_perms
        try:
            ToolsConfig.extracts_phone_extract_perms = ["999999"]
            self.assertEqual(Extract.get_rights("query"), ["999999"])
            self.assertEqual(perms("phoneExtract", "query"), ["131103"])
        finally:
            ToolsConfig.extracts_phone_extract_perms = original
