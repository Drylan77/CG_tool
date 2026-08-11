# CG Asset Renamer — Maya 2025.3

Outil de **renommage** et de **vérification** des noms d'assets pour le
département modeling / surfacing. Le modeler sélectionne un ou plusieurs
objets, ouvre l'outil, remplit une petite fenêtre de paramètres, et l'objet
est renommé selon une **convention de nommage centralisée et réutilisable**.
L'outil permet aussi de **checker** si les noms existants sont conformes.

> Compatible **Maya 2025.3** (Python 3.11, PySide6 / Qt6).

---

## 1. Aperçu

La fenêtre propose :

| Paramètre            | Exemple            | Requis |
|----------------------|--------------------|:------:|
| Name of the object   | `hand`             |  oui   |
| Place / Position     | `Top / Bot / L / R…` | non  |
| Surface type         | `metal / plastic / glass…` | oui |
| Color                | `grey / black / red…` | non  |
| Type                 | `GEO / PT / FX…`   |  oui   |

Un **aperçu en temps réel** montre le nom final avant de l'appliquer, par ex. :

```
hand_L_metal_grey_GEO
```

En sélection multiple, un index numérique est ajouté automatiquement pour
garantir l'unicité :

```
screw_metal_01_GEO
screw_metal_02_GEO
screw_metal_03_GEO
```

---

## 2. La convention de nommage

Format général (les éléments optionnels vides sont simplement omis) :

```
<name>_<place>_<surface>_<color>_[index]_<TYPE>
   │       │        │        │       │       └── suffixe identifiant (toujours en dernier)
   │       │        │        │       └────────── index numérique automatique (batch)
   │       │        │        └────────────────── couleur dominante (optionnel)
   │       │        └─────────────────────────── matériau / surface (requis)
   │       └──────────────────────────────────── position (optionnel)
   └──────────────────────────────────────────── nom descriptif, un seul mot camelCase (requis)
```

Règles appliquées (validité Maya) :

- caractères autorisés : lettres, chiffres, `_` uniquement ;
- ne peut pas commencer par un chiffre ;
- pas d'espaces ni de caractères spéciaux (nettoyés automatiquement) ;
- `name` est un mot unique (`engine block` → `engineblock`) ;
- pas de noms réservés Maya (`persp`, `top`, `front`, `side`…).

### Pourquoi ce format ?

- Le **type en suffixe** (`GEO`, `PT`, `FX`…) permet de filtrer/trier vite,
  et de reconnaître la nature d'un node d'un coup d'œil.
- Chaque valeur de liste (`metal`, `grey`, `L`…) provient d'un **vocabulaire
  contrôlé et disjoint** : le checker identifie donc chaque slot par sa valeur,
  ce qui rend les champs optionnels sûrs à omettre sans ambiguïté.

---

## 3. La convention est un fichier — réutilisable et modifiable

Toute la convention vit dans **`config/naming_convention.json`**. Pas besoin de
toucher au code pour :

- ajouter une surface (`carbon`, `chrome`…) ou une couleur ;
- ajouter/retirer un token, changer l'ordre, le séparateur ;
- rendre un champ requis ou optionnel.

La fenêtre se régénère automatiquement à partir de ce fichier. Vous pouvez
distribuer un JSON commun à toute l'équipe (voir la variable d'environnement
`CG_RENAMER_CONFIG` ci-dessous) pour garantir la **même convention partout**.

---

## 4. Installation

### Méthode simple (glisser-déposer)

1. Récupérez le dossier de l'outil sur votre machine.
2. Faites glisser **`install.py`** dans le viewport de Maya.
3. Un bouton **`CGRenamer`** est ajouté à la shelf courante, et l'outil s'ouvre.

L'installeur ajoute aussi le chemin à votre `userSetup.py`, donc l'import
fonctionne après redémarrage.

### Méthode manuelle

Dans le Script Editor (onglet Python) :

```python
import sys
sys.path.append(r"CHEMIN/VERS/CG_tool/src")
import cg_renamer.launch as launch
launch.main()
```

### Convention partagée par l'équipe (optionnel)

Pointez tout le monde vers le même JSON via une variable d'environnement
(dans `Maya.env` ou l'environnement système) :

```
CG_RENAMER_CONFIG=//serveur/pipeline/naming/naming_convention.json
```

---

## 5. Utilisation

**Renommer**
1. Sélectionnez le(s) objet(s) dans Maya.
2. Ouvrez l'outil, remplissez les champs (aperçu en direct).
3. Cliquez **RENAME selection**.

**Vérifier (check)**
- **Check selection** : contrôle les objets sélectionnés.
- **Check scene** : contrôle tous les transforms de la scène.
- Le tableau liste chaque nom, `OK` / `INVALID`, et le détail des erreurs.
- Double-cliquez une ligne pour **sélectionner l'objet** correspondant dans Maya.

---

## 6. Structure du projet

```
CG_tool/
├── config/
│   └── naming_convention.json     # LA convention (éditable, réutilisable)
├── src/cg_renamer/
│   ├── naming_convention.py       # cœur logique (build / parse / validate) — sans Maya
│   ├── maya_utils.py              # wrappers maya.cmds
│   ├── renamer.py                 # opérations rename / check
│   ├── renamer_ui.py              # fenêtre PySide6 (générée depuis le JSON)
│   └── launch.py                  # point d'entrée
├── tests/
│   └── test_naming_convention.py  # tests unitaires (hors Maya)
├── install.py                     # installeur glisser-déposer + bouton shelf
└── README.md
```

Le cœur logique est **indépendant de Maya** : les tests tournent avec un simple
`python -m unittest`, sans session Maya.

```bash
python -m unittest discover tests -v
```

---

## 7. Pistes d'évolution (recherche / idées)

Cette V1 se concentre sur *renommer + checker*, comme demandé. Idées pour la
suite, classées par valeur :

1. **Auto-fix / batch-fix** — bouton « corriger » qui propose et applique le
   nom conforme le plus proche pour chaque objet `INVALID`.
2. **Détection du type automatique** — pré-remplir le champ `Type` en
   inspectant le node (mesh → `GEO`, nurbsCurve → `CRV`, joint → `JNT`…).
3. **Détection de doublons** dans la scène + surlignage.
4. **Presets par département** (Modeling, Surfacing, Layout…) : plusieurs JSON
   sélectionnables dans un menu déroulant.
5. **Renommage de la hiérarchie / des shapes** en même temps que le transform
   (garder `objShape` cohérent).
6. **Export d'un rapport** de conformité (CSV / JSON) pour la revue de scène.
7. **Intégration pipeline** : validation à la publication (hook avant export
   Alembic / USD) pour bloquer les noms non conformes.
8. **Support namespaces / références** et gestion des collisions inter-assets.
9. **Undo groupé** : encapsuler un batch de renommage dans un seul `undoChunk`.
10. **Règles de casse strictes** (camelCase forcé sur `name`, UPPER sur `type`)
    avec normalisation automatique.

Dis-moi lesquelles t'intéressent et je les ajoute.
