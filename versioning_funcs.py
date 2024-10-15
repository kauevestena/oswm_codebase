from functions import *
import osmapi


class GetDatetimeLastUpdate:

    default_return = (
        -1,
        default_missing_day,
        default_missing_month,
        default_missing_year,
    )

    def __init__(self):
        self.api = osmapi.OsmApi()

    def get_datetime_last_update_way(self, featureid):
        try:
            res = self.api.WayGet(featureid)
            dt = res["timestamp"]  # date time object
            return res["version"], dt.day, dt.month, dt.year
        except Exception as e:
            print(e)
            return self.default_return

    def get_datetime_last_update_node(self, featureid):
        try:
            res = self.api.NodeGet(featureid)
            dt = res["timestamp"]  # date time object
            return res["version"], dt.day, dt.month, dt.year
        except Exception as e:
            print(e)
            return self.default_return


# def get_datetime_last_update(
#     featureid,
#     featuretype="way",
#     onlylast=True,
#     return_parsed=True,
#     return_special_tuple=True,
# ):
#     # TODO: use osmapi!

#     h_url = get_feature_history_url(featureid, featuretype)

#     try:
#         response = requests.get(h_url)
#     except:
#         if onlylast:
#             if return_parsed and return_special_tuple:
#                 return [None] * 4  # 4 Nones

#             return ""
#         else:
#             return []

#     if response.status_code == 200:
#         tree = ElementTree.fromstring(response.content)

#         element_list = tree.findall(featuretype)

#         if element_list:
#             date_rec = [element.attrib["timestamp"][:-1] for element in element_list]

#             if onlylast:
#                 if return_parsed:
#                     if return_special_tuple:
#                         # parsed = datetime.strptime(date_rec[-1],'%Y-%m-%dT%H:%M:%S')
#                         parsed = parse_datetime_str(date_rec[-1])
#                         return len(date_rec), parsed.day, parsed.month, parsed.year

#                     else:
#                         # return datetime.strptime(date_rec[-1],'%Y-%m-%dT%H:%M:%S')
#                         return parse_datetime_str(date_rec[-1])

#                 else:
#                     return date_rec[-1]

#             else:
#                 if return_parsed:
#                     return [parse_datetime_str(record) for record in date_rec]

#                 else:
#                     return date_rec

#         else:
#             if onlylast:
#                 return ""
#             else:
#                 return []

#     else:
#         print("bad request, check feature id/type")
#         if onlylast:
#             return ""
#         else:
#             return []


# def get_datetime_last_update_node(featureid):
#     # all default options
#     return get_datetime_last_update(featureid, featuretype="node")
