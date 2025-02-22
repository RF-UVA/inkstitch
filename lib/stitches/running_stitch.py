# Authors: see git history
#
# Copyright (c) 2010 Authors
# Licensed under the GNU GPL version 3.0 or later.  See the file LICENSE for details.

import math
import typing
from copy import copy

import numpy as np
from shapely import geometry as shgeo
from ..utils import prng

""" Utility functions to produce running stitches. """


def split_segment_even_n(a, b, segments: int, jitter_sigma: float = 0.0, random_seed=None) -> typing.List[shgeo.Point]:
    if segments <= 1:
        return []
    line = shgeo.LineString((a, b))

    splits = np.array(range(1, segments)) / segments
    if random_seed is not None:
        jitters = (prng.nUniformFloats(len(splits), random_seed) * 2) - 1
        splits = splits + jitters * (jitter_sigma / segments)

    # sort the splits in case a bad roll transposes any of them
    return [line.interpolate(x, normalized=True) for x in sorted(splits)]


def split_segment_even_dist(a, b, max_length: float, jitter_sigma: float = 0.0, random_seed=None) -> typing.List[shgeo.Point]:
    distance = shgeo.Point(a).distance(shgeo.Point(b))
    segments = math.ceil(distance / max_length)
    return split_segment_even_n(a, b, segments, jitter_sigma, random_seed)


def split_segment_random_phase(a, b, length: float, length_sigma: float, random_seed: str) -> typing.List[shgeo.Point]:
    line = shgeo.LineString([a, b])
    progress = length * prng.uniformFloats(random_seed, "phase")[0]
    splits = [progress]
    distance = line.length
    if progress >= distance:
        return []
    for x in prng.iterUniformFloats(random_seed):
        progress += length * (1 + length_sigma * (x - 0.5) * 2)
        if progress >= distance:
            break
        splits.append(progress)
    return [line.interpolate(x, normalized=False) for x in splits]


def running_stitch(points, stitch_length, tolerance):
    """Generate running stitch along a path.

    Given a path and a stitch length, walk along the path in increments of the
    stitch length.  If sharp corners are encountered, an extra stitch will be
    added at the corner to avoid rounding the corner.  The starting and ending
    point are always stitched.

    The path is described by a set of line segments, each connected to the next.
    The line segments are described by a sequence of points.
    """

    if len(points) < 2:
        return []

    # simplify will remove as many points as possible while ensuring that the
    # resulting path stays within the specified tolerance of the original path.
    path = shgeo.LineString(points)
    simplified = path.simplify(tolerance, preserve_topology=False)

    # save the points that simplify picked and make sure we stitch them
    important_points = set(simplified.coords)
    important_point_indices = [i for i, point in enumerate(points) if point.as_tuple() in important_points]

    output = []
    for start, end in zip(important_point_indices[:-1], important_point_indices[1:]):
        # consider sections of the original path, each one starting and ending
        # with an important point
        section = points[start:end + 1]
        if not output or output[-1] != section[0]:
            output.append(section[0])

        # Now split each section up evenly into stitches, each with a length no
        # greater than the specified stitch_length.
        section_ls = shgeo.LineString(section)
        section_length = section_ls.length
        if section_length > stitch_length:
            # a fractional stitch needs to be rounded up, which will make all
            # the stitches shorter
            num_stitches = math.ceil(section_length / stitch_length)
            actual_stitch_length = section_length / num_stitches

            distance = actual_stitch_length

            segment_start = section[0]
            for segment_end in section[1:]:
                segment = segment_end - segment_start
                segment_length = segment.length()

                if distance < segment_length:
                    segment_direction = segment.unit()

                    while distance < segment_length:
                        output.append(segment_start + distance * segment_direction)
                        distance += actual_stitch_length

                distance -= segment_length
                segment_start = segment_end

    if points[-1] != output[-1]:
        output.append(points[-1])

    return output


def bean_stitch(stitches, repeats):
    """Generate bean stitch from a set of stitches.

    "Bean" stitch is made by backtracking each stitch to make it heavier.  A
    simple bean stitch would be two stitches forward, one stitch back, two
    stitches forward, etc.  This would result in each stitch being tripled.

    We'll say that the above counts as 1 repeat.  Backtracking each stitch
    repeatedly will result in a heavier bean stitch.  There will always be
    an odd number of threads piled up for each stitch.

    Repeats is a list of a repeated pattern e.g. [0, 1, 3] doesn't repeat the first stitch,
    goes back and forth on the second stitch, goes goes 3 times back and forth on the third stitch,
    and starts the pattern again by not repeating the fourth stitch, etc.
    """

    if len(stitches) < 2:
        return stitches

    repeat_list_length = len(repeats)
    repeat_list_pos = 0

    new_stitches = [stitches[0]]

    for stitch in stitches:
        new_stitches.append(stitch)

        for i in range(repeats[repeat_list_pos]):
            new_stitches.extend(copy(new_stitches[-2:]))

        repeat_list_pos += 1
        if repeat_list_pos == repeat_list_length:
            repeat_list_pos = 0

    return new_stitches
