import csv
import logging
import multiprocessing as mp
import numpy as np
import os

from PIL import Image, ImageDraw, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True

from time import perf_counter

# The number of crops per multicrop
MULTICROP_COUNT = 1

# The scale factor for each multicrop
MULTICROP_SCALE_FACTOR = 1.5

CANVAS_WIDTH = 720
CANVAS_HEIGHT = 480

logging.basicConfig(filename='crop.log', level=logging.DEBUG)

# TODO: reimplement for future study
def predict_crop_size(sv_image_y):
    """
    # Calculate distance from point to image center
    dist_to_center = math.sqrt((x-im_width/2)**2 + (y-im_height/2)**2)
    # Calculate distance from point to center of left edge
    dist_to_left_edge = math.sqrt((x-0)**2 + (y-im_height/2)**2)
    # Calculate distance from point to center of right edge
    dist_to_right_edge = math.sqrt((x - im_width) ** 2 + (y - im_height/2) ** 2)

    min_dist = min([dist_to_center, dist_to_left_edge, dist_to_right_edge])

    crop_size = (4.0/15.0)*min_dist + 200

    print("Min dist was "+str(min_dist))
    """
    crop_size = 0
    distance = max(0, 19.80546390 + 0.01523952 * sv_image_y)

    if distance > 0:
        crop_size = 8725.6 * (distance ** -1.192)
    if crop_size > 1500 or distance == 0:
        crop_size = 1500
    if crop_size < 50:
        crop_size = 50

    return crop_size

def get3dFov(zoom):
    # use linear descent if zoom <= 2 else experimental parameters
    return 126.5 - (zoom * 36.75) if zoom <= 2 else 195.93 / (1.92 ** zoom)

def sgn(x):
    return 1 if x >= 0 else -1

def calculatePointPov(canvasX, canvasY, pov, canvas_dim):
    heading, pitch, zoom = pov["heading"], pov["pitch"], pov["zoom"]

    PI = np.pi
    cos = np.cos
    sin = np.sin
    tan = np.tan
    sqrt = np.sqrt
    atan2 = np.arctan2
    asin = np.arcsin

    fov = get3dFov(zoom) * PI / 180.0
    width = canvas_dim["width"]
    height = canvas_dim["height"]

    h0 = heading * PI / 180.0
    p0 = pitch * PI / 180.0

    f = 0.5 * width / tan(0.5 * fov)

    x0 = f * cos(p0) * sin(h0)
    y0 = f * cos(p0) * cos(h0)
    z0 = f * sin(p0)

    du = canvasX - width / 2
    dv = height / 2 - canvasY

    ux = sgn(cos(p0)) * cos(h0)
    uy = -sgn(cos(p0)) * sin(h0)
    uz = 0

    vx = -sin(p0) * sin(h0)
    vy = -sin(p0) * cos(h0)
    vz = cos(p0)

    x = x0 + du * ux + dv * vx
    y = y0 + du * uy + dv * vy
    z = z0 + du * uz + dv * vz

    R = sqrt(x * x + y * y + z * z)
    h = atan2(x, y)
    p = asin(z / R)

    return {
        "heading": h * 180.0 / PI,
        "pitch": p * 180.0 / PI,
        "zoom": zoom
    }

def label_point(label_pov, photographer_pov, img_dim):
    horizontal_scale = 2 * np.pi / img_dim[0]
    amplitude = photographer_pov["pitch"] * img_dim[1] / 180

    original_x = round((label_pov["heading"] - photographer_pov["heading"]) / 180 * img_dim[0] / 2 + img_dim[0] / 2) % img_dim[0]
    original_y = round(img_dim[1] / 2 + amplitude * np.cos(horizontal_scale * original_x))

    point = np.array([original_x, original_y])
    cosine_slope = amplitude * -np.sin(horizontal_scale * original_x) * horizontal_scale
    normal_slope = -1 / cosine_slope
    offset_vec = np.array([1, normal_slope])
    if normal_slope < 0:
        offset_vec *= -1
    print(offset_vec)
    
    normalized_offset_vec = offset_vec / np.linalg.norm(offset_vec)
    offset_vec_scalar = -label_pov["pitch"] / 180 * img_dim[1]

    final_offset_vec = normalized_offset_vec * offset_vec_scalar
    final_point = point + final_offset_vec

    return round(final_point[0]), round(final_point[1])

def make_crop(pano_img_path, label_pov, photographer_heading, photographer_pitch, destination_dir, label_name, lock, multicrop=True, draw_mark=True):
    crop_names = []
    try:
        im = Image.open(pano_img_path)
        draw = ImageDraw.Draw(im)

        # im_width = im.size[0]
        # im_height = im.size[1]
        # print(im_width, im_height)
        img_dim = im.size
        im_width = im.size[0]
        im_height = im.size[1]

        # predicted_crop_size = predict_crop_size(sv_image_y)
        # crop_width = int(predicted_crop_size)
        # crop_height = int(predicted_crop_size)
        crop_width = 1500
        crop_height = 1500

        # Work out scaling factor based on image dimensions
        # scaling_factor = im_width / 13312
        # sv_image_x *= scaling_factor
        # sv_image_y *= scaling_factor
        
        photographer_pov = {
            "heading": photographer_heading,
            "pitch": photographer_pitch
        }

        x, y = label_point(label_pov, photographer_pov, img_dim)
        print(x, y)

        r = 20
        if draw_mark:
            lock.acquire()
            draw.ellipse((x - r, y - r, x + r, y + r), fill=128)
            im.save(pano_img_path)
            lock.release()

        for i in range(MULTICROP_COUNT):
            top_left_x = int(x - crop_width / 2)
            top_left_y = int(y - crop_height / 2)
            if multicrop:
                crop_name = label_name + "_" + str(i) + ".jpg"
            else:
                crop_name = label_name + ".jpg"
            crop_destination = os.path.join(destination_dir, crop_name)
            if not os.path.exists(crop_destination) and 0 <= top_left_y and top_left_y + crop_height <= im_height:
                crop = Image.new('RGB', (crop_width, crop_height))
                if top_left_x < 0:
                    crop_1 = im.crop((top_left_x + im_width, top_left_y, im_width, top_left_y + crop_height))
                    crop_2 = im.crop((0, top_left_y, top_left_x + crop_width, top_left_y + crop_height))
                    crop.paste(crop_1, (0,0))
                    crop.paste(crop_2, (- top_left_x, 0))
                elif top_left_x + crop_width > im_width:
                    crop_1 = im.crop((top_left_x, top_left_y, im_width, top_left_y + crop_height))
                    crop_2 = im.crop((0, top_left_y, top_left_x + crop_width - im_width, top_left_y + crop_height))
                    crop.paste(crop_1, (0,0))
                    crop.paste(crop_2, (im_width - top_left_x, 0))
                else:
                    crop = im.crop((top_left_x, top_left_y, top_left_x + crop_width, top_left_y + crop_height))
                crop.save(crop_destination)
                print("Successfully extracted crop to " + crop_name)
                logging.info(label_name + " " + pano_img_path + " " + str(x) + " " + str(y))
                logging.info("---------------------------------------------------")
                crop_names.append(crop_name)
            else:
                print("Failed to extract crop to " + crop_name)
            if not multicrop:
                break
            crop_width = int(crop_width * MULTICROP_SCALE_FACTOR)
            crop_height = int(crop_height * MULTICROP_SCALE_FACTOR)
        im.close()
    except Exception as e:
        print(e)
        print("Error for {}".format(pano_img_path))

    return crop_names, (x, y), img_dim

def bulk_extract_crops(data_chunk, path_to_gsv_scrapes, destination_dir, output_csv, panos):
    t_start = perf_counter()
    row_count = len(data_chunk)

    # make the output directory if needed
    if not os.path.isdir(destination_dir):
        os.makedirs(destination_dir)

    with mp.Manager() as manager:
        # get cpu core count
        cpu_count = mp.cpu_count()

        # Create interprocess list to store output csv rows.
        output_rows = manager.list()

        lock = mp.Lock()

        # split data_chunk into sub-chunks for multiprocessing
        i = 0
        processes = []
        while i < row_count:
            chunk_size = (row_count - i) // cpu_count
            labels = data_chunk.iloc[i:i + chunk_size, :]
            process = mp.Process(target=crop_label_subset, args=(labels, output_rows, path_to_gsv_scrapes, destination_dir, lock))
            processes.append(process)
            cpu_count -= 1
            i += chunk_size

        # start processes
        for p in processes:
            p.start()

        # join processes once finished
        for p in processes:
            p.join()

        # create writer to write output csv with crop info
        # TODO: for now, we will just have image_name point to a cropped jpg as model input 
        # and label_type as the output
        successful_crop_count = len(output_rows)
        no_pano_fail = (row_count * MULTICROP_COUNT) - successful_crop_count
        with open(output_csv, 'a+', newline='') as csv_out:
            csv_w = csv.writer(csv_out)
            for row in output_rows:
                # row format: [crop_name, primary_label_type, pano_id, label_id, final_sv_position, pano_size]
                csv_w.writerow(row[:3])

                # update final sv position per label
                if row[2] in panos and row[3] in panos[row[2]].feats:
                    if panos[row[2]].width is None and panos[row[2]].height is None:
                        panos[row[2]].update_pano_size(row[5][0], row[5][1])

                    label = panos[row[2]].feats[row[3]]
                    label.finalize_sv_position(row[4][0], row[4][1])

        t_stop = perf_counter()
        execution_time = t_stop - t_start

        print("Finished Cropping.")
        print()
        
        return [row_count, successful_crop_count, no_pano_fail, execution_time]

def crop_label_subset(input_rows, output_rows, path_to_gsv_scrapes, destination_dir, lock):
    counter = 0
    process_pid = os.getpid()
    input_rows_dict = input_rows.to_dict('records')
    for row in input_rows_dict:
        counter += 1
        row = list(row.values())
        pano_id = row[0]
        canvas_x = int(row[3])
        canvas_y = int(row[4])
        canvas_width = int(row[5])
        canvas_height = int(row[6])
        zoom = int(row[7])
        label_type = int(row[8])
        photographer_heading = float(row[9])
        photographer_pitch = float(row[10])
        camera_heading = float(row[11])
        camera_pitch = float(row[12])

        pano_img_path = os.path.join(path_to_gsv_scrapes, pano_id + ".jpg")

        camera_pov = {
            "heading": camera_heading,
            "pitch": camera_pitch,
            "zoom": zoom
        }

        canvas_dim = {
            "width": canvas_width,
            "height": canvas_height
        }

        label_pov = calculatePointPov(canvas_x, canvas_y, camera_pov, canvas_dim)

        # Extract the crop
        if os.path.exists(pano_img_path):
            crop_names = []
            if not label_type == 0:
                # TODO: currently the only case being supported
                label_name = str(row[13])
                crop_names, pos, pano_size = make_crop(pano_img_path, label_pov, photographer_heading, photographer_pitch, destination_dir, label_name, lock, True, False)
            else:
                # TODO: this may need to be its own function since null cropping should be independent
                # In order to uniquely identify null crops, we concatenate the pid of process they
                # were generated on and the counter within the process to the name of the null crop.
                label_name = "null_" + str(process_pid) + "_" +  str(counter)
                crop_names, pos, pano_size = make_crop(pano_img_path, label_pov, photographer_heading, photographer_pitch, destination_dir, label_name, lock, False, False)

            for crop_name in crop_names:
                output_rows.append([crop_name, label_type, pano_id, int(label_name), pos, pano_size])
        else:
            print("Panorama image not found.")
            try:
                logging.warning("Skipped label id " + label_name + " due to missing image.")
            except NameError:
                logging.warning("Skipped null crop " + str(process_pid) + " " + str(counter) + " due to missing image.")
