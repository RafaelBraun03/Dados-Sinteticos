import bpy
import bpy_extras
import random
import math
import os
import time
from mathutils import Vector, Euler

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO
# ---------------------------------------------------------------------------

TEMPLATES_COLLECTION = "Templates"
SPAWNED_COLLECTION = "Spawned"
SPAWN_AREA_NAME = "SpawnArea"
LIGHT_NAME = "Light"

TEMPLATES = ["Phillips", "Allen", "Sextavado"]
CLASS_IDS = {"Phillips": 0, "Allen": 1, "Sextavado": 2}

COUNT_MIN_PER_TYPE = 0   # pode não ter nenhum parafuso de um tipo na imagem
COUNT_MAX_PER_TYPE = 4

MIN_GAP = 0.001    # folga mínima (m) entre os "raios" de dois parafusos
MAX_TRIES = 30     # tentativas de posição antes de desistir e colocar mesmo assim

LIGHT_POWER_MIN = 6.0     # Watts - calibrado em torno dos 11W originais da cena
LIGHT_POWER_MAX = 18.0
LIGHT_COLOR_TEMP_MIN = 0.85   # mais alaranjado/quente
LIGHT_COLOR_TEMP_MAX = 1.15   # mais azulado/frio

TRAY_NAME = "Bandeja"
TRAY_MATERIAL_NAME = "BandejaMat"
METAL_PROBABILITY = 0.5   # chance de sortear acabamento metálico em vez de plástico

# metal: bem metálico, superfície de fosca a semi-polida, tom acinzentado/prateado
METAL_ROUGHNESS_RANGE = (0.15, 0.45)
METAL_GRAY_RANGE = (0.35, 0.75)

# plástico: sem metallic, mais fosco, cor livre
PLASTIC_ROUGHNESS_RANGE = (0.35, 0.8)
PLASTIC_COLOR_RANGE = (0.1, 0.9)

RENDER_ENGINE = "CYCLES"
RENDER_DEVICE = "CPU"          # sem GPU, por decisão do Rafael
RENDER_SAMPLES = 64            # começa moderado; pode subir depois se sobrar qualidade/tempo
RENDER_WIDTH = 640
RENDER_HEIGHT = 640
RENDER_USE_DENOISING = True    # ajuda a disfarçar ruído com poucos samples

# --- Geração do dataset (loop) ---
DATASET_ROOT = r"C:\Users\rafae\DocumentsPC\dataset"
NUM_IMAGES = 10          # teste pequeno por enquanto
TRAIN_SPLIT = 0.8        # 80% train / 20% valid


# ---------------------------------------------------------------------------
# SPAWN DOS PARAFUSOS
# ---------------------------------------------------------------------------

def get_or_create_collection(name):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    new_col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(new_col)
    return new_col


def clear_collection(collection):
    for obj in list(collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def get_spawn_bounds():
    spawn_obj = bpy.data.objects[SPAWN_AREA_NAME]
    world_corners = [spawn_obj.matrix_world @ v.co for v in spawn_obj.data.vertices]
    xs = [v.x for v in world_corners]
    ys = [v.y for v in world_corners]
    zs = [v.z for v in world_corners]
    return {
        "x_min": min(xs), "x_max": max(xs),
        "y_min": min(ys), "y_max": max(ys),
        "z": max(zs),
    }


def lowest_point_offset(obj):
    rot_matrix = obj.rotation_euler.to_matrix()
    return min((rot_matrix @ v.co).z for v in obj.data.vertices)


def footprint_half_extent(obj):
    rot_matrix = obj.rotation_euler.to_matrix()
    corners = [rot_matrix @ Vector(corner) for corner in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    return (max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2


def random_resting_rotation():
    STANDING_PROBABILITY = 0.1
    azimuth = random.uniform(0.0, 2 * math.pi)

    if random.random() < STANDING_PROBABILITY:
        tilt = math.radians(random.uniform(-8, 8))         # quase em pé
    else:
        tilt = math.radians(90 + random.uniform(-15, 15))  # quase deitado

    return Euler((tilt, 0.0, azimuth), 'XYZ')


def spawn_screws(bounds):
    spawned_collection = get_or_create_collection(SPAWNED_COLLECTION)
    clear_collection(spawned_collection)

    templates_collection = bpy.data.collections[TEMPLATES_COLLECTION]
    placed = []
    counts = {}

    for template_name in TEMPLATES:
        template_obj = templates_collection.objects[template_name]
        count = random.randint(COUNT_MIN_PER_TYPE, COUNT_MAX_PER_TYPE)
        counts[template_name] = count

        for i in range(count):
            new_obj = template_obj.copy()
            new_obj.data = template_obj.data.copy()
            new_obj.name = f"{template_name}_{i}"
            
            # Grava o ID da classe diretamente no objeto para a anotação
            new_obj["class_id"] = CLASS_IDS[template_name]
            
            spawned_collection.objects.link(new_obj)

            new_obj.rotation_euler = random_resting_rotation()

            half_x, half_y = footprint_half_extent(new_obj)
            own_radius = math.hypot(half_x, half_y)

            x_min, x_max = bounds["x_min"] + half_x, bounds["x_max"] - half_x
            y_min, y_max = bounds["y_min"] + half_y, bounds["y_max"] - half_y
            if x_min > x_max:
                x_min = x_max = (bounds["x_min"] + bounds["x_max"]) / 2
            if y_min > y_max:
                y_min = y_max = (bounds["y_min"] + bounds["y_max"]) / 2

            for attempt in range(MAX_TRIES):
                x = random.uniform(x_min, x_max)
                y = random.uniform(y_min, y_max)
                if all(math.hypot(x - px, y - py) >= own_radius + p_radius + MIN_GAP
                       for px, py, p_radius in placed):
                    break
            else:
                print(f"{new_obj.name}: não achou posição livre, "
                      f"colocando mesmo assim (pode sobrepor).")

            placed.append((x, y, own_radius))

            offset = lowest_point_offset(new_obj)
            new_obj.location = (x, y, bounds["z"] - offset)

    return counts


# ---------------------------------------------------------------------------
# VARIAÇÃO DE LUZ
# ---------------------------------------------------------------------------

def randomize_light():
    light_obj = bpy.data.objects[LIGHT_NAME]
    light_data = light_obj.data

    power = random.uniform(LIGHT_POWER_MIN, LIGHT_POWER_MAX)
    light_data.energy = power

    warm_cool = random.uniform(LIGHT_COLOR_TEMP_MIN, LIGHT_COLOR_TEMP_MAX)
    r = min(1.0, 1.0 * (2.0 - warm_cool))
    b = min(1.0, 1.0 * warm_cool)
    g = 1.0
    light_data.color = (r, g, b)


# ---------------------------------------------------------------------------
# MATERIAL DA BANDEJA
# ---------------------------------------------------------------------------

def get_or_create_tray_material():
    if TRAY_MATERIAL_NAME in bpy.data.materials:
        mat = bpy.data.materials[TRAY_MATERIAL_NAME]
    else:
        mat = bpy.data.materials.new(TRAY_MATERIAL_NAME)
        mat.use_nodes = True

    tray_obj = bpy.data.objects[TRAY_NAME]
    if tray_obj.data.materials:
        tray_obj.data.materials[0] = mat
    else:
        tray_obj.data.materials.append(mat)

    return mat


def randomize_tray_material():
    mat = get_or_create_tray_material()
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        return

    is_metal = random.random() < METAL_PROBABILITY

    if is_metal:
        metallic = random.uniform(0.85, 1.0)
        roughness = random.uniform(*METAL_ROUGHNESS_RANGE)
        gray = random.uniform(*METAL_GRAY_RANGE)
        tint = random.uniform(-0.03, 0.03)
        color = (gray + tint, gray, gray - tint, 1.0)
    else:
        metallic = 0.0
        roughness = random.uniform(*PLASTIC_ROUGHNESS_RANGE)
        color = (
            random.uniform(*PLASTIC_COLOR_RANGE),
            random.uniform(*PLASTIC_COLOR_RANGE),
            random.uniform(*PLASTIC_COLOR_RANGE),
            1.0,
        )

    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Base Color"].default_value = color


# ---------------------------------------------------------------------------
# ANOTAÇÃO YOLO
# ---------------------------------------------------------------------------

def get_yolo_bbox(scene, cam, obj):
    """
    Projeta os 8 cantos da bounding box 3D do objeto para o plano da câmera 2D
    e retorna no formato (x_center, y_center, width, height) normalizado de 0 a 1.
    """
    matrix = obj.matrix_world
    # Coordenadas globais dos cantos da caixa delimitadora do objeto
    corners_3d = [matrix @ Vector(corner) for corner in obj.bound_box]
    
    # Projeta para coordenadas 2D da câmera
    coords_2d = [bpy_extras.object_utils.world_to_camera_view(scene, cam, c) for c in corners_3d]
    
    # X cresce da esquerda para a direita (0 a 1)
    xs = [c.x for c in coords_2d]
    # O Blender tem Y crescendo de baixo pra cima. YOLO espera Y de cima pra baixo.
    ys = [1.0 - c.y for c in coords_2d] 
    
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    
    # Limita as bordas entre 0.0 e 1.0 para não estourar a imagem se o parafuso ficar na beira
    x_min = max(0.0, min(1.0, x_min))
    x_max = max(0.0, min(1.0, x_max))
    y_min = max(0.0, min(1.0, y_min))
    y_max = max(0.0, min(1.0, y_max))
    
    width = x_max - x_min
    height = y_max - y_min
    
    # Descarta objetos que ficaram completamente invisíveis/fora do campo (w ou h zerado)
    if width <= 0.0 or height <= 0.0:
        return None
        
    x_center = x_min + (width / 2.0)
    y_center = y_min + (height / 2.0)
    
    return (x_center, y_center, width, height)


# ---------------------------------------------------------------------------
# RENDER E EXECUÇÃO DO LOOP
# ---------------------------------------------------------------------------

def configure_render_settings():
    scene = bpy.context.scene
    scene.render.engine = RENDER_ENGINE
    scene.cycles.device = RENDER_DEVICE
    scene.cycles.samples = RENDER_SAMPLES
    scene.cycles.use_denoising = RENDER_USE_DENOISING
    scene.render.resolution_x = RENDER_WIDTH
    scene.render.resolution_y = RENDER_HEIGHT
    scene.render.resolution_percentage = 100


def get_dataset_dirs():
    dirs = {
        "train_images": os.path.join(DATASET_ROOT, "train", "images"),
        "train_labels": os.path.join(DATASET_ROOT, "train", "labels"),
        "valid_images": os.path.join(DATASET_ROOT, "valid", "images"),
        "valid_labels": os.path.join(DATASET_ROOT, "valid", "labels"),
    }
    for path in dirs.values():
        os.makedirs(path, exist_ok=True)
    return dirs


def build_split_assignment():
    num_train = round(NUM_IMAGES * TRAIN_SPLIT)
    num_valid = NUM_IMAGES - num_train
    assignment = ["train"] * num_train + ["valid"] * num_valid
    random.shuffle(assignment)
    return assignment


def format_duration(seconds):
    seconds = int(round(seconds))
    minutes, sec = divmod(seconds, 60)
    if minutes:
        return f"{minutes}min {sec}s"
    return f"{sec}s"


def generate_dataset():
    bounds = get_spawn_bounds()
    dirs = get_dataset_dirs()
    configure_render_settings()
    assignment = build_split_assignment()
    
    scene = bpy.context.scene
    cam = bpy.data.objects['Camera']
    spawned_collection = bpy.data.collections.get(SPAWNED_COLLECTION)

    start_time = time.time()
    durations = []

    for i in range(NUM_IMAGES):
        split = assignment[i]
        counts = spawn_screws(bounds)
        randomize_light()
        randomize_tray_material()

        # Força o depsgraph a atualizar (essencial para as bounding boxes usarem a posição correta)
        bpy.context.view_layer.update()

        base_filename = f"img_{i:04d}"
        image_path = os.path.join(dirs[f"{split}_images"], f"{base_filename}.png")
        label_path = os.path.join(dirs[f"{split}_labels"], f"{base_filename}.txt")

        # Escreve o arquivo .txt com as anotações
        with open(label_path, 'w') as f:
            for obj in spawned_collection.objects:
                if "class_id" not in obj:
                    continue
                    
                bbox = get_yolo_bbox(scene, cam, obj)
                if bbox:
                    xc, yc, w, h = bbox
                    f.write(f"{obj['class_id']} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")

        # Renderiza a imagem
        img_start = time.time()
        bpy.context.scene.render.filepath = image_path
        bpy.ops.render.render(write_still=True)
        
        img_duration = time.time() - img_start
        durations.append(img_duration)

        avg_duration = sum(durations) / len(durations)
        remaining = NUM_IMAGES - (i + 1)
        eta = avg_duration * remaining

        total = sum(counts.values())
        resumo = ", ".join(f"{tipo}={qtd}" for tipo, qtd in counts.items())
        print(f"[Imagem {i + 1} de {NUM_IMAGES}] ({split}) {base_filename}: "
              f"{total} parafusos ({resumo}) | "
              f"render: {img_duration:.1f}s | ETA: {format_duration(eta)}")

    total_duration = time.time() - start_time
    print(f"\nDataset gerado em: {DATASET_ROOT}")
    print(f"  tempo total: {format_duration(total_duration)}")
    print(f"  train: {round(NUM_IMAGES * TRAIN_SPLIT)} imagens e labels")
    print(f"  valid: {NUM_IMAGES - round(NUM_IMAGES * TRAIN_SPLIT)} imagens e labels")

if __name__ == "__main__":
    generate_dataset()