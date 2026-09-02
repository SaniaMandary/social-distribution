[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/bRZK9dqv)
CMPUT404-project-socialdistribution
===================================

CMPUT404-project-socialdistribution

See [the web page](https://uofa-cmput404.github.io/general/project.html) for a description of the project.

Make a distributed social network!

**Social Distribution**

A distributed social networking platform built with Django, where independent "nodes" (servers) communicate with each other over a REST API so users on different servers can follow, share posts, comment, and interact.

**Overview**

Unlike a typical social media app that runs on a single server, this project implements inter-node communication: each node maintains its own database and user base, but nodes can talk to each other through a documented REST API to share posts, follow requests, likes, and comments across servers. The project includes two independently running nodes (db_node_a, db_node_b) to demonstrate and test this federation in practice.

**Features**

User authentication and profiles
Create, edit, and delete posts (public, friends-only, or private visibility)
Follow / friend requests across nodes
Likes and comments on posts, synced across nodes
Inter-node REST API for server-to-server communication
Admin approval flow for connecting new remote nodes


## License

* MIT License.

## Copyright

The authors claiming copyright, if they wish to be known, can list their names here...

* Balpreet Singh Juneja
* Rabewar Moradi
* Sania Mandary
* Allison McGilvery
* Ganesh Saraswat
* Reon Nguyen

## Collaborations:

lab3
lab4
