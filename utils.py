import cv2
import string
import random
import numpy as np
from collections import deque
from operator import itemgetter
from scipy.optimize import linear_sum_assignment

import person

w = 640
h = 480

body_labels = {
    0: "nose",
    1: "lEye",
    2: "rEye",
    3: "lEar",
    4: "rEar",
    5: "lShoulder",
    6: "rShoulder",
    7: "lElbow",
    8: "rElbow",
    9: "lWrist",
    10: "rWrist",
    11: "lHip",
    12: "rHip",
    13: "lKnee",
    14: "rKnee",
    15: "lAnkle",
    16: "rAnkle",
    17: "neck",
}
body_idx = dict([[v, k] for k, v in body_labels.items()])


def id_gen(size=6, chars=string.ascii_uppercase + string.digits):
    """
    https://pythontips.com/2013/07/28/generating-a-random-string/
    input: id_gen(3, "6793YUIO")
    output: 'Y3U'
    """
    return "".join(random.choice(chars) for x in range(size))


def IOU(boxA, boxB):
    # pyimagesearch: determine the (x, y)-coordinates of the intersection rectangle
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    # compute the area of intersection rectangle
    interArea = max(0, xB - xA + 1) * max(0, yB - yA + 1)

    # compute the area of both the prediction and ground-truth
    # rectangles
    boxAArea = (boxA[2] - boxA[0] + 1) * (boxA[3] - boxA[1] + 1)
    boxBArea = (boxB[2] - boxB[0] + 1) * (boxB[3] - boxB[1] + 1)

    # compute the intersection over union by taking the intersection
    # area and dividing it by the sum of prediction + ground-truth
    # areas - the interesection area
    iou = interArea / float(boxAArea + boxBArea - interArea)

    # return the intersection over union value
    return iou


def get_bbox(kp_list):
    bbox = []
    for aggs in [min, max]:
        for idx in range(2):
            bound = aggs(kp_list, key=itemgetter(idx))[idx]
            bbox.append(bound)
    return bbox

class img_obj(object):
    def __init__(self, offset=50):
        self.offset = 50
        self.fontScale = 1
        self.thickness = 2
        self.box_color = (195, 195, 89)
        self.text_color = (151, 187, 106)
        self.centroid_color = (223, 183, 190)

    def annotate(self, tracker, image, boxes):
        """
        Used to return image with
        person instances designated 
        by the bounding box and a 
        marker at the centroid.
        Annotated with tracker id
        and activity label
        """
        for row in topology:
            try:
                a_idx, b_idx = row[2:]
                a_part, b_part = (
                    body_labels[int(a_idx.data.cpu().numpy())],
                    body_labels[int(b_idx.data.cpu().numpy())],
                )
                a_coord, b_coord = tracker.pose_dict[a_part], tracker.pose_dict[b_part]
                cv2.line(image, a_coord, b_coord, tracker.skeleton_color, 2)
            except KeyError:
                pass

        if boxes:
            try:
                x1, y1, x2, y2 = tracker.bbox
                image = cv2.rectangle(
                    image,
                    (x1 - self.offset, y1 - self.offset),
                    (x2 + self.offset, y2 + self.offset),
                    self.box_color,
                    2,
                )
                image = cv2.drawMarker(
                    image, tracker.centroid, self.centroid_color, 0, 30, self.thickness
                )
                cv2.putText(
                    image,
                    tracker.id,
                    (x1 - self.offset, y1 - self.offset),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    self.fontScale,
                    self.text_color,
                    self.thickness,
                )
                cv2.putText(
                    image,
                    str(tracker.activity),
                    (x1 - self.offset, y1 - self.offest),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    self.fontScale,
                    self.text_color,
                    self.thickness,
                )
            except:
                pass

        return image

    def get_crop(self, bbox, image):
        """
        Helper for sampling image crops
        """
        return image[x1:x2, y1:y2, :]


def update_trackers(trackers, bboxes):
    track_boxes = [tracker.bbox for tracker in trackers]
    matched, unmatched_trackers, unmatched_detections = tracker_match(
        track_boxes, [b[0] for b in bboxes]
    )

    for idx, jdx in matched:
        trackers[idx].set_bbox(bboxes[jdx][0])
        trackers[idx].set_pose(bboxes[jdx][1])

    for idx in unmatched_detections:
        try:
            trackers[idx].count += 1
            if trackers[idx].count > trackers[idx].expiration:
                trackers.pop(idx)
        except:
            pass

    for idx in unmatched_trackers:
        p = person.PersonTracker()
        p.set_bbox(bboxes[idx][0])
        p.set_pose(bboxes[idx][1])
        trackers.append(p)
    return trackers

def source_capture(source):
    source = int(source) if source.isdigit() else source
    cap = cv2.VideoCapture(source)
    fourcc_cap = cv2.VideoWriter_fourcc(*"MJPG")
    cap.set(cv2.CAP_PROP_FOURCC, fourcc_cap)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    return cap

def tracker_distance(prev_roi, curr_roi, metric=IOU):
    distance_matrix = np.zeros((len(prev_roi), len(curr_roi)), dtype=np.float32)
    for t, trk in enumerate(prev_roi):
        for d, det in enumerate(curr_roi):
            distance_matrix[t, d] = metric(trk, det)
    return distance_matrix


def tracker_match(prev_roi, curr_roi, threshold=0.3):
    """
    From previously tracked regions of interest and current detections,
    output matched detections, unmatched trackers, unmatched detections.
    """

    distance_matrix = tracker_distance(prev_roi, curr_roi)

    # Hungarian algorithm (also known as Munkres algorithm)
    rowIdxs, colIdxs = linear_sum_assignment(-distance_matrix)

    unmatched_trackers = list(set(range(len(prev_roi))).difference(rowIdxs))
    unmatched_detections = list(set(range(len(curr_roi))).difference(colIdxs))

    matches = []
    for m in list(zip(rowIdxs, colIdxs)):
        if distance_matrix[m[0], m[1]] < threshold:
            unmatched_trackers.append(m[0])
            unmatched_detections.append(m[1])
        else:
            matches.append(np.array(m).reshape(1, 2))

    if len(matches) == 0:
        matches = np.empty((0, 2), dtype=int)
    else:
        matches = np.concatenate(matches, axis=0)

    return matches, np.array(unmatched_detections), np.array(unmatched_trackers)

class PersonTracker(object):
    def __init__(self):
        self.id = id_gen()
        self.q = deque(maxlen=10)
        return

    def set_bbox(self, bbox):
        self.bbox = bbox
        x1, y1, x2, y2 = bbox
        self.h = 1e-6 + x2 - x1
        self.w = 1e-6 + y2 - y1
        self.centroid = tuple(map(int, (x1 + self.h / 2, y1 + self.w / 2)))
        return

    def update_pose(self, pose_dict):
        ft_vec = np.zeros(2 * len(body_labels))
        for ky in pose_dict:
            idx = body_idx[ky]
            ft_vec[2 * idx : 2 * (idx + 1)] = (
                2
                * (np.array(pose_dict[ky]) - np.array(self.centroid))
                / np.array((self.h, self.w))
            )
        self.q.append(ft_vec)
        return

    def annotate(self, image):
        x1, y1, x2, y2 = self.bbox
        image = cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 255), 3)
        image = cv2.putText(
            image,
            self.activity,
            (x1, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 0, 255),
            2,
        )
        image = cv2.drawMarker(image, self.centroid, (255, 0, 0), 0, 30, 4)
        return image
