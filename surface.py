""" This module contains functions and structures for detecting and transforming the playing surface """

# Import standard libraries
import numpy as np
import cv2
import imutils
from copy import deepcopy
from datetime import datetime

# Set the cutoff limit for detected surfaces
# e.g. 0.5 means a surface is only valid if it occupies at
# least half of the entire image space from the original image
cutoff = 0.03

class PlayingSurface:
    " Structure to store information about the playing surface. "

    def __init__(self):
        self.name = "playing_surface_name"
        self.transform = []  # Transformed image of the playing surface
        self.contour = []  # Contour of the playing surface wrt original image
        self.img_cnt = []  # Image with contour overlayed on original image
        self.area = []  # Area of the playing surface
        self.area_relative = []  # Relative size of the playing surface wrt original image
        self.perspective_matrix = []
        self.width = []
        self.height = []
        self.dealer_region = []
        self.player_region = []

def detect(image):
    " This function finds the playing surface in the original image and stores info in an appropriate object "

    # The image will be set to this height for faster processing
    image_resize_value = 300.0

    # Work out how much bigger than 'x' the image is wrt height
    ratio = image.shape[0] / image_resize_value

    # Make a copy of the original image at its full size
    original_image = deepcopy(image)

    # Resize the image (should be a reduction, but not strictly important)
    image = imutils.resize(image, height=int(image_resize_value))

    # Convert the image to grayscale, apply a blur and then find edges
    im_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    im_blur = cv2.bilateralFilter(im_gray, 11, 17, 17)
    im_edge = cv2.Canny(im_blur, 30, 200)

    # Find contours in the edged image and only keep the largest five (ordered largest to smallest)
    _, contours, _ = cv2.findContours(im_edge.copy(), cv2.RETR_TREE,
                                      cv2.CHAIN_APPROX_SIMPLE)

    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

    # Initialise an index to represent the location of the playing surface in the contours list
    contour_idx = 0

    # Initialise the polymetric approximation accuracy scaling factor
    POLY_ACC_CONST = 0.02

    surface_cnt = None

    for c in contours:

        # Approximate the contour
        perimeter = cv2.arcLength(c, closed=True)
        curr_cnt = cv2.approxPolyDP(c, POLY_ACC_CONST * perimeter, closed=True)

        # If our approximated contour has four points, then we can assume that we have found our target
        # because the contours are ordered largest to smallest and we want the largest four-point contour
        if len(curr_cnt) == 4:
            # Draw the contour over the image (to be displayed later)
            # image = im_edge
            cv2.drawContours(image, contours, contourIdx=contour_idx, color=(255, 180, 0), thickness=2)
            surface_cnt = curr_cnt
            break

        # Increment the index
        contour_idx += 1

    # Even if there're contours but none of them are 4 points, we want to
    # return
    if surface_cnt is None:
        return None

    # Now that we have our contour, we need to determine the top-left, top-right, bottom-right, and
    # bottom-left points so that we can later warp the image -- we'll start by reshaping our contour
    # to be our finals and initializing our output rectangle in top-left, top-right, bottom-right,
    # and bottom-left order
    rect_points = surface_cnt.reshape(4, 2)

    # The top-left point has the smallest sum whereas the bottom-right has the largest sum
    s = np.sum(rect_points, axis=1)
    top_left_point = rect_points[np.argmin(s)]
    bottom_right_point = rect_points[np.argmax(s)]

    temp = None
    reduced_points = None

    for i in range(rect_points.shape[0]):
        if np.array_equal(rect_points[i], top_left_point):
            temp = np.delete(rect_points, i, 0)
            break

    for i in range(temp.shape[0]):
        if np.array_equal(temp[i], bottom_right_point):
            reduced_points = np.delete(temp, i, 0)
            break

    # Compute the difference between the points -- the top-right will have the minimum difference
    # and the bottom-left will have the maximum difference
    diff = np.diff(reduced_points, axis=1)
    top_right_point = reduced_points[np.argmin(diff)]
    bottom_left_point = reduced_points[np.argmax(diff)]

    # Scale points up to full size
    top_left_point = np.multiply(top_left_point, ratio)
    top_right_point = np.multiply(top_right_point, ratio)
    bottom_right_point = np.multiply(bottom_right_point, ratio)
    bottom_left_point = np.multiply(bottom_left_point, ratio)

    # Put all the points into a single 4 x 2 ndarray
    rect = np.array([top_left_point, top_right_point, bottom_right_point, bottom_left_point], dtype="float32")

    # Compute the width of the new image
    widthA = np.sqrt(((bottom_right_point[0] - bottom_left_point[0]) ** 2) +
                     ((bottom_right_point[1] - bottom_left_point[1]) ** 2))
    widthB = np.sqrt(((top_right_point[0] - top_left_point[0]) ** 2) +
                     ((top_right_point[1] - top_left_point[1]) ** 2))
    width = max(int(widthA), int(widthB))

    # Compute the height of the new image
    heightA = np.sqrt(((top_right_point[0] - bottom_right_point[0]) ** 2) +
                      ((top_right_point[1] - bottom_right_point[1]) ** 2))
    heightB = np.sqrt(((top_left_point[0] - bottom_left_point[0]) ** 2) +
                      ((top_left_point[1] - bottom_left_point[1]) ** 2))
    height = max(int(heightA), int(heightB))

    height = 800
    width = int(1.8 * height)

    # Configure the four points of the destination image for the transform function
    # Noting that the origin is the top-left point with x positive to the right and
    # y positive downwards
    dst = np.array([
        # top-left point
        [0, 0],
        # top-right point
        [width - 1, 0],
        # bottom-right point
        [width - 1, height - 1],
        # bottom-left point
        [0, height - 1]], dtype="float32")

    # calculate the perspective transform matrix and warp the perspective to grab
    # a birds-eye view of the surface
    # Noting that rect and dst must have their points in the same order
    persp_mtx = cv2.getPerspectiveTransform(rect, dst)
    transformed = cv2.warpPerspective(original_image, persp_mtx, (width, height))

    # Get the area of the surface (pixels^2)
    transformed_area = cv2.contourArea(surface_cnt)

    # Get the area of the original image for a comparison (pixels^2)
    original_image_area = original_image.shape[0] * original_image.shape[1]

    # Compute the relative size of the surface wrt the entire image
    relative_size = np.divide(transformed_area, original_image_area)

    if relative_size < cutoff:
        return None
    else:

        # Create a new instance of the playing surface class
        playing_surface = PlayingSurface()
        # Give it a name
        playing_surface.name = 'primary'
        # Store the contour of the playing surface
        playing_surface.contour = surface_cnt
        # Store the contour drawn over the image
        playing_surface.img_cnt = image
        # Store the transformed playing surface
        playing_surface.transform = transformed
        # Store the area of the surface (pixels^2)
        playing_surface.area = transformed_area
        # Store the relative size of the playing surface wrt the entire image
        playing_surface.area_relative = relative_size
        # Store the perspective matrix used to get the transformation
        playing_surface.perspective_matrix = persp_mtx
        # Store the width of the transformed image
        playing_surface.width = width
        # Store the height of the transformed image
        playing_surface.height = height
        playing_surface.dealer_region = np.array([0, int(width / 2)])
        playing_surface.player_region = np.array([int((width / 2) + 1), int(width)])

        # Return the complete playing surface object
        return playing_surface


def display(countdown, contoured, transformed=np.array([])):
    # Arbitrary x, y offsets for displays
    x_offset = 50
    y_offset = 50

    # Original image from source with countdown timer
    cv2.imshow("Original", countdown)
    cv2.moveWindow("Original", x_offset, y_offset)

    # Original image with the contour of the playing surface overlayed
    cv2.imshow("Contoured", contoured)
    cv2.moveWindow("Contoured", countdown.shape[1] + x_offset, y_offset)

    # Only show the transformed surface if it exists (given to function implies existence)
    if bool(transformed.any()):
        # Transformed playing surface
        cv2.imshow("Transformed", transformed)
        cv2.moveWindow("Transformed", countdown.shape[1] * 2 + x_offset, y_offset)

    return


def timer(image, count):

    text = format(count, '02d')
    font_pos = (380, 70)
    # Give the font a little shadow to help it stand out
    shadow_offset = 2
    a = int(font_pos[0]) + shadow_offset
    b = int(font_pos[1]) + shadow_offset
    font_pos2 = (a, b)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 2
    font_thickness = 3
    line_type = cv2.LINE_AA

    # Make the font red near the end of the countdown (white otherwise)
    if count <= 10 and count % 2 == 0:
        colour = (0, 0, 255)
    elif count <= 3:
        colour = (0, 0, 255)
    else:
        colour = (255, 255, 255)

    # Add text to the image with a small shadow
    cv2.putText(image, text, font_pos2, font, font_scale, (0, 0, 0), font_thickness, line_type)
    cv2.putText(image, text, font_pos, font, font_scale, colour, font_thickness, line_type)

    # Return the image with the text overlayed
    return image


def get_surface(cap, count):
    count += 1
    curr_time = float(datetime.now().strftime('%s.%f')[9:-5])
    # initialise an empty playing surface
    valid_surface = None

    while count != 0:

        # Initialise or reinitialise the surface each time we grab a new frame
        playing_surface = None

        # take camera image
        (flag_, image) = cap.read()

        # Try and obtain a valid playing surface object
        playing_surface = detect(image)

        # Configure the raw original image
        orig_disp = deepcopy(imutils.resize(image, height=300))

        # Start with a fresh copy of the raw original image
        timer_disp = deepcopy(orig_disp)
        test_time = float(datetime.now().strftime('%s.%f')[9:-5])
        if count != 0 and abs(test_time - curr_time) > 1:
            curr_time = float(datetime.now().strftime('%s.%f')[9:-5])
            count -= 1
        timer_disp = timer(timer_disp, count)

        if playing_surface:
            # Configure and display the contoured and transformed images if the playing surface was found
            cnt_disp = deepcopy(imutils.resize(playing_surface.img_cnt, height=300))
            trans_disp = deepcopy(imutils.resize(playing_surface.transform, height=300))
            display(timer_disp, cnt_disp, trans_disp)
            valid_surface = playing_surface
        else:
            # Add a text overlay in place of the contour image
            not_found_overlay = not_found(deepcopy(orig_disp))
            if valid_surface is not None:
                display(timer_disp, not_found_overlay, imutils.resize(
                    valid_surface.transform, height=300))
            else:
                # Display the countdown timer and the raw original until a valid surface is found
                display(timer_disp, not_found_overlay)

        # handling closing of displays in main atm, could shift anywhere though
        key = cv2.waitKey(delay=1)

        # keep displaying images until user enters 'q'
        if key == ord('a') or key == ord('A'):
            cv2.destroyAllWindows()
            break

    cv2.destroyAllWindows()

    return valid_surface


def not_found(image):

    text = 'Playing surface not found!'
    font_pos = (10, image.shape[0] - 20)
    # Give the font a little shadow to help it stand out
    shadow_offset = 1
    a = int(font_pos[0]) + shadow_offset
    b = int(font_pos[1]) + shadow_offset
    font_pos2 = (a, b)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1
    font_thickness = 2
    line_type = cv2.LINE_AA
    colour = (0, 0, 255)

    # Add text to the image with a small shadow
    cv2.putText(image, text, font_pos2, font, font_scale, (0, 0, 0), font_thickness, line_type)
    cv2.putText(image, text, font_pos, font, font_scale, colour, font_thickness, line_type)

    # Return the image with the text overlayed
    return image
