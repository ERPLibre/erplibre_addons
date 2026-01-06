# DEVOPS definition

## Plan - Planifier et définir

La planification initiale, définissant les objectifs et les exigences du projet.

## Code - Développer

Le développement du code source, où les développeurs écrivent le code nécessaire pour mettre en œuvre les
fonctionnalités du logiciel.

## Build - Package

La création du logiciel à partir du code source, généralement à l'aide d'outils de build automatisés.

## Test - Tester

Les tests, y compris les tests unitaires, les tests d'intégration et les tests de système, pour s'assurer que le
logiciel fonctionne correctement.

## Release - Livrable

La préparation du logiciel pour le déploiement, y compris la gestion des versions et la documentation associée.

## Deploy - Déploiement

Le déploiement du logiciel dans l'environnement de production.

## Operate - Opération

Les actions nécessaires pour maintenir l'application en cours d'exécution de manière fiable. L'exploitation continue du
logiciel en production, surveillant les performances et assurant un bon fonctionnement.

Cette étape concerne la gestion continue et le maintien en bon état de fonctionnement de l'application dans l'
environnement de production. Les équipes responsables de l'exploitation surveillent les performances en temps réel,
gèrent les incidents, effectuent des tâches de maintenance planifiées et réagissent aux problèmes qui peuvent survenir
pendant l'utilisation normale. L'objectif principal est de garantir que l'application est disponible, fonctionne
correctement et répond aux besoins des utilisateurs.

## Monitor - Surveillance

La collecte d'information pour évaluer les performances et détecter tout problème éventuel.

Cette étape consiste à observer et à collecter des données sur les performances de l'application en production. Cela
inclut la surveillance des métriques, des journaux, des alertes et d'autres indicateurs clés pour évaluer la santé du
système. La surveillance permet de détecter les problèmes potentiels, d'analyser les tendances, et d'obtenir des
informations sur le comportement de l'application en temps réel. Les données recueillies lors de cette étape peuvent
également fournir des informations précieuses pour l'optimisation continue du système.

# Gestion de menu de l'application erplibre_devops

## DevOps

Gestion des workspaces de travail, des systèmes machines, etc...

## Plan

TODO Un outil pour permettre de planifier la création de module.

## Code

TODO Un outil pour permettre le suivi du développement, le déverminage, l'assistance à la construction de code.

## Build

TODO Afficher les outils de packages, exemple tel que les dockers.

## Test

TODO Afficher la liste des tests pour les projets et voir les rapports de tests.

## Release

TODO Ensemble de procédure et suivi des versions des différentes livrables.

## Deploy

TODO Suivi pour le déploiement en production, automatisation et sécurité.

## Operate

TODO Suivi des états des instances en temps réels.

## Monitor

TODO Suivi des états de l'historique d'exécution des instances.

## Configuration

Les pages de configurations sur l'ensemble de l'application.

# Technopoïèse

Work in progress

auto :

-   exec DONE
-   dévermineur/debug DONE
-   logging WIP
-   error DONE
-   modification/update DONE
-   constructeur/build WIP
-   codeur/code DONE
-   libre/freedom WIP
-   correcteur/fix WIP
-   refactor MISSING
-   publish MISSING
-   reverse MISSING
-   data MISSING
-   plan MISSING
-   operate MISSING
-   monitor MISSING
-   distribué/deploy MISSING
-   release MISSING
-   test MISSING
-   doc MISSING

# Configuration

Mettre dans `config.conf`

Obligatoire

```server_wide_modules = base,web,queue_job```

Facultatif

```
workers = 2

[queue_job]
channels = root:2
```
