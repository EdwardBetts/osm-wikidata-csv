#!/usr/bin/python3

import csv
import requests
import sys
import html
import lxml.etree
import configparser

from requests.auth import HTTPBasicAuth

api_base_url = "https://api.openstreetmap.org/api/0.6"
config = configparser.ConfigParser()


def get_auth():
    return HTTPBasicAuth(config["osm"]["username"], config["osm"]["password"])


def get_osm_object(osm_type, osm_id):
    r = requests.get(f"{api_base_url}/{osm_type}/{osm_id}", auth=get_auth())
    try:
        return lxml.etree.fromstring(r.content)
    except lxml.etree.XMLSyntaxError:
        print(r.text)
        sys.exit(-1)


def osm_put(path, data):
    return requests.put(api_base_url + path, auth=get_auth(), data=data)


def new_changeset(comment):
    return f"""
<osm>
  <changeset>
    <tag k="comment" v="{html.escape(comment)}"/>
  </changeset>
</osm>"""


def create_changeset(changeset):
    try:
        return osm_put("/changeset/create", data=changeset.encode("utf-8"))
    except requests.exceptions.HTTPError as r:
        print(changeset)
        print(r.response.text)
        raise


def close_changeset(changeset_id):
    return osm_put(f"/changeset/{changeset_id}/close", data='')


def save_element(osm_type, osm_id, element_data):
    r = osm_put(f"/{osm_type}/{osm_id}", data=element_data)
    reply = r.text.strip()
    if reply.isdigit():
        return
    print(f"error updating {osm_type}")
    print(reply)
    sys.exit(-1)


def skip_existing(root, osm_type, osm_id, qid):
    existing_wikidata_tag = root.find('.//tag[@k="wikidata"]')
    if existing_wikidata_tag is None:
        return False
    existing_wikidata = existing_wikidata_tag.get("v")
    if existing_wikidata == qid:
        print(f"skipping {osm_type}/{osm_id}, it is already tagged")
        return True

    print(f"error {osm_type}/{osm_id} has a different wikidata tag")
    sys.exit(-1)


def get_osm_objects(csv_filename):
    file_iter = open(csv_filename)
    csv_reader = csv.reader(file_iter)
    next(file_iter)  # headings

    update_relations = []
    for qid, osm_type, osm_id in csv_reader:
        print(qid, osm_type, osm_id)
        root = get_osm_object(osm_type, osm_id)
        if skip_existing(root, osm_type, osm_id, qid):
            continue

        root[0].append(lxml.etree.Element("tag", k="wikidata", v=qid))
        update_relations.append((osm_type, osm_id, root))


def process_csv(filename):
    config.read("config")

    update_objects = get_osm_objects(filename)

    print("starting changeset")
    changeset = new_changeset(config["osm"]["changeset_comment"])
    r = create_changeset(changeset)
    changeset_id = r.text.strip()

    for osm_type, osm_id, root in update_objects:
        root[0].set("changeset", changeset_id)
        element_data = lxml.etree.tostring(root)
        print(f"updating {osm_type}/{osm_id}")
        save_element(osm_type, osm_id, element_data)

    close_changeset(changeset_id)
    print("closing changeset")


if __name__ == "__main__":
    process_csv(sys.argv[1])
