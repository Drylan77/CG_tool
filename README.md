# Naming Tool — Maya 2025.3 (Pipeline VFX / Modeling)

Outil Python pour **Autodesk Maya 2025.3** qui aide les modeleurs à **nommer**,
**valider** et **corriger** le naming de leurs assets selon une convention de
type studio VFX. Objectif : rendre le *bon* nommage plus rapide que le mauvais,
et bloquer en amont les problèmes qui cassent le pipeline (`pCube1`,
duplicate names, exports Alembic/USD, `final_final`).

- **Python 3.11 / PySide6 (Qt6)** — fenêtre dockable parentée à Maya.
- **Convention 100% pilotée par un fichier de config** — changez le JSON, tout
  se reconfigure (regex, presets UI, checks) sans toucher au code.
- **API headless** pour intégration dans un script de publish.

---

## 1. La convention

```
[side]_[descriptor][increment]_[SUFFIX]
```

| Token | Requis | Description | Exemples |
|-------|:------:|-------------|----------|
| `side` | optionnel | latéralité | `L`, `R`, `C`, `F`/`B`, `T`/`Bt` |
| `descriptor` | **oui** | description **camelCase**, du général au spécifique | `doorHandle`, `wheelFront` |
| `increment` | optionnel | numéro à padding fixe, commence à `01` | `chairLeg01` |
| `SUFFIX` | **oui** | type de nœud, MAJUSCULES | `GEO`, `GRP`, `LOC`… |

**Valides :** `L_doorHandle_GEO`, `wheelFront01_GEO`, `C_body_GEO`, `chassis_GRP`
**Invalides :** `pCube1`, `Door Handle_geo`, `1stFloor_GEO`, `handle_GEO1`

Suffixes par défaut : `GEO GRP LOC CRV NRB PLY CAM LGT JNT CTL MAT SG TEX DEF CNS PXY`.
Compat USD/Alembic par construction (identifiants `[A-Za-z0-9_]`, pas de chiffre
initial, pas de namespaces) ; groupes `geo_/proxy_/guide_GRP` → purposes USD
`render/proxy/guide`.

---

## 2. Installation

**Glisser-déposer :** faites glisser `install_drag_drop.py` dans le viewport de
Maya → un bouton shelf **NamingTool** est créé et l'outil s'ouvre.

**Manuel :**
```python
import sys; sys.path.append(r"CHEMIN/VERS/CG_tool")
import namingTool; namingTool.show()
```

**Config partagée équipe :** variable d'environnement
`NAMINGTOOL_CONFIG=//serveur/pipeline/naming_config.json` (deep-merge sur les
valeurs par défaut).

---

## 3. Fonctionnalités

### Onglet Renamer
- **Rename & Number** : `base01_GEO`, `base02_GEO`… dans l'ordre de sélection.
- **Prefix / Suffix rapides** : boutons presets (sides + suffixes) anti-doublon.
- **Search & Replace** : sélection / hiérarchie / scène, wildcards, casse.
- **Auto Suffix** *(fonction phare)* : inspecte le type réel de chaque nœud
  (mesh→`GEO`, group→`GRP`, curve→`CRV`, locator→`LOC`…) et applique/corrige le
  bon suffixe.
- **Side by BBox** : préfixe `L_`/`R_` selon le centre X du bounding box.
- **Cleanup** : caractères illégaux, `-`/espace → camelCase, `pasted__`,
  namespaces, shapes désynchronisées.
- Tout est **undoable en un seul Ctrl+Z**.

### Onglet Validator (sanity check)
Portée **Selection / Hierarchy / Scene**. Chaque check : ✅/⚠️/❌ + liste
**cliquable** des nœuds fautifs (clic = select) + **Fix** quand automatisable.

1. Noms par défaut Maya (`pCube*`, `polySurface*`, `group*`…)
2. Duplicate short names
3. Suffixe manquant / invalide
4. Suffixe incohérent avec le type réel
5. Caractères illégaux / casse / `__` / `_` final
6. Shapes désynchronisées (`ball_GEO` ↔ `pCubeShape3`)
7. Namespaces présents
8. Hiérarchie (géo orpheline au monde, groupes vides)
9. Numérotation incohérente (padding mixte)
10. *(bonus)* transforms GEO non freezés

Boutons **Run All**, **Select Errors**, **Export Report** (`.json` / `.txt`).

### Mode headless (publish)
```python
from namingTool.core import checks
report = checks.run_all(scope="scene")   # {check: {"status","nodes","message","fixable"}}
if any(r["status"] == "error" for r in report.values()):
    raise RuntimeError("Naming errors — publish bloqué.")
```

---

## 4. Architecture

```
namingTool/
├── __init__.py            # namingTool.show()
├── launch.py              # workspaceControl dockable
├── core/
│   ├── config.py          # load/save/merge JSON (defaults embarqués)
│   ├── naming.py          # regex centrale, parse/build/validate — SANS Maya
│   ├── maya_utils.py      # helpers maya.cmds partagés (undo, introspection)
│   ├── renamer.py         # opérations de rename (undo chunks)
│   └── checks.py          # 10 checks + fixes + API headless
├── ui/                    # PySide6 : main_window, renamer_tab, validator_tab
└── resources/naming_config.json
install_drag_drop.py
tests/test_naming.py       # 17 tests (hors Maya)
```

Une **regex unique** dérivée de la config est partagée par le renamer et le
validator (aucune duplication de logique). Le cœur est testable sans Maya :

```bash
python -m unittest discover tests -v
```

---

## 5. Configuration (`naming_config.json`)

Extrait :
```json
{
  "separator": "_", "case": "camelCase", "padding": 2,
  "sides": {"left": "L", "right": "R", "center": "C"},
  "suffixes": {"geometry": "GEO", "group": "GRP", "locator": "LOC", "...": "..."},
  "node_type_suffix": {"mesh": "GEO", "nurbsCurve": "CRV", "joint": "JNT"},
  "lod_token": {"enabled": false, "pattern": "lod{n}"},
  "forbidden_words": ["final", "new", "test", "temp", "copy", "pasted"],
  "protected_nodes": ["persp", "top", "front", "side"]
}
```
Changer `"geometry": "GEO"` → `"MSH"` reconfigure regex, presets et checks.

---

## 6. Nommage des fichiers (rappel, hors périmètre de l'outil)

```
<SHOW>_<assetType>_<assetName>_<step>_<variant>_<lod>_<version>.<ext>
ex : TOTRS_prop_chair_model_main_lod0_v003.ma
```
WIP : `<asset>_<step>_<descriptor>_v###_<initiales>.ma`. Versions en `v###`,
jamais `final` / `new` / `ok2`.
