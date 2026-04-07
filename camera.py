import numpy as np
from pyrr import Matrix44, Quaternion

class Camera:
    def __init__(self, screen_size):
        self.screen_size = screen_size
        self.z_up_to_y_up = Matrix44.from_x_rotation(np.pi / 2)
        self.model_offset = np.array([0, 0, 0], dtype="f4")
        self.reset_view()

    def reset_view(self):
        self.target = np.array([0.0, 0.0, 0.0], dtype="f4") # Focus point (look-at)
        self.azimuth = 0.0
        self.elevation = 0.2
        self.radius = 5.0
        self.model_quat = Quaternion()

    def orbit(self, dx, dy):
        """ Spherical orbit around the target (camera focus) """
        sensitivity = 0.005
        self.azimuth -= dx * sensitivity
        self.elevation -= dy * sensitivity
        # Clamp elevation to prevent flipping
        self.elevation = max(-1.45, min(1.45, self.elevation))

    def pan(self, dx, dy):
        """ Move target along camera axes for panning """
        # Pan speed is proportional to zoom level
        pan_speed = self.radius * 0.0015
        
        cos_az = np.cos(self.azimuth)
        sin_az = np.sin(self.azimuth)
        
        # Local camera Right and Up vectors
        right = np.array([cos_az, 0.0, -sin_az], dtype="f4")
        up = np.array([0.0, 1.0, 0.0], dtype="f4")
        
        self.target -= right * dx * pan_speed
        self.target += up * dy * pan_speed


    def zoom(self, wheel_y):
        """ Smoothly scaling distance to target """
        self.radius = max(0.05, self.radius * (1.0 - wheel_y * 0.1))

    def get_position(self):
        cos_el = np.cos(self.elevation)
        sin_el = np.sin(self.elevation)
        sin_az = np.sin(self.azimuth)
        cos_az = np.cos(self.azimuth)
        
        ex = self.target[0] + self.radius * cos_el * sin_az
        ey = self.target[1] + self.radius * sin_el
        ez = self.target[2] + self.radius * cos_el * cos_az
        return np.array([ex, ey, ez], dtype="f4")

    def get_view_matrix(self):
        eye = self.get_position()
        return Matrix44.look_at(tuple(eye), tuple(self.target), (0.0, 1.0, 0.0))

    def get_projection_matrix(self):
        return Matrix44.perspective_projection(
            45.0, self.screen_size[0] / self.screen_size[1], 0.01, 10000.0
        )

    def get_model_matrix(self):
        """
        Calculates Model Matrix ensuring rotation occurs around the GEOMETRIC CENTER.
        Formula: Final_Translate(Feet-to-Y0) * Rotation * Initial_Translate(Center-to-Origin) * ZtoY
        """
        try:
            h = self._last_height
            cx, cy, cz = self._last_center_raw
            gy = self._last_ground_y
        except AttributeError:
            h = 2.0
            cx, cy, cz = (0.0, 1.0, 0.0)
            gy = 0.0

        # Point that will be at (0,0,0) during rotation is the geometric center
        t_to_center_origin = Matrix44.from_translation([-cx, -cy, -cz])
        rot_mat = self.model_quat.matrix44
        
        # Point that was at 'gy' should be at Y=0 after scaling/centering.
        # Height of center above ground is (cy - gy).
        t_to_ground = Matrix44.from_translation([0, cy - gy, 0])
        
        return t_to_ground * rot_mat * t_to_center_origin * self.z_up_to_y_up

    def frame_model(self, all_vertices):
        if not all_vertices or len(all_vertices) == 0:
            return
        
        combined = np.vstack(all_vertices)
        # 1. Advanced Orientation Analysis (Longest axis = Vertical)
        mn_raw, mx_raw = combined.min(0), combined.max(0)
        extents_raw = mx_raw - mn_raw
        
        # Determine the longest axis (0:X, 1:Y, 2:Z)
        longest_axis = np.argmax(extents_raw)
        
        # Transformation matrix to make the longest axis the 'Y' (Vertical) axis
        # We ensure the Head remains on +Y by using correct rotation directions
        if longest_axis == 0: # X is longest
            # Rotate around Z to put X on Y. We use -90 degrees so +X becomes +Y
            self.z_up_to_y_up = Matrix44.from_z_rotation(-np.pi / 2)
            rot_mat = np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1]], "f4")
        elif longest_axis == 2: # Z is longest (Standard GTA)
            # Rotate around X to put Z on Y. We use -90 degrees so +Z becomes +Y
            self.z_up_to_y_up = Matrix44.from_x_rotation(-np.pi / 2)
            rot_mat = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], "f4")
        else: # Y is already longest
            self.z_up_to_y_up = Matrix44.identity()
            rot_mat = np.eye(3, dtype="f4")

        # Apply transformation for analysis
        v_aligned = (rot_mat @ combined.T).T

        # 2. Advanced Feet Detection (Ground Alignment)
        mn, mx = v_aligned.min(0), v_aligned.max(0)
        height = mx[1] - mn[1]
        
        # Take the lowest 10% of vertices
        threshold = mn[1] + height * 0.1
        low_v = v_aligned[v_aligned[:, 1] < threshold]
        
        if len(low_v) > 20:
            # Simple 2-cluster split by X center to find average foot height
            mid_x = (mn[0] + mx[0]) * 0.5
            left_foot = low_v[low_v[:, 0] < mid_x]
            right_foot = low_v[low_v[:, 0] >= mid_x]
            
            # Use the average of the lowest points in each cluster as the "ground"
            if len(left_foot) > 0 and len(right_foot) > 0:
                ground_y = (np.min(left_foot[:, 1]) + np.min(right_foot[:, 1])) * 0.5
            else:
                ground_y = mn[1]
        else:
            ground_y = mn[1]

        # 3. Save raw stats for pivot calculations
        center = (mn + mx) * 0.5
        self._last_height = height
        self._last_center_raw = center
        self._last_ground_y = ground_y
        
        # 4. Auto-Face Camera (Front Orientation)
        extents = mx - mn
        if extents[2] > extents[0] * 1.2:
            self.model_quat = Quaternion.from_y_rotation(-np.pi / 2)
        else:
            self.model_quat = Quaternion.from_y_rotation(0.0)
            
        # 5. Framing
        # Target is the center relative to ground
        self.target = np.array([0, center[1] - ground_y, 0], dtype="f4")
        fov_rad = np.radians(45.0)
        self.radius = max(height / (2.0 * np.tan(fov_rad / 2.0)) * 1.6, 1.5)
        self.azimuth = 0.0
        self.elevation = 0.2

    def rotate_in_camera_space(self, dy, dx):
        step = np.pi / 2
        # Use simpler model rotation along world axes for consistency
        if dx != 0:
            q = Quaternion.from_y_rotation(-dx * step)
            self.model_quat = q * self.model_quat
        if dy != 0:
            q = Quaternion.from_x_rotation(dy * step)
            self.model_quat = q * self.model_quat
        self.model_quat = self.model_quat.normalised

    def set_model_face(self, name):
        FACES = {
            "frente": (0.0, np.pi), # Adjusted for our 180 flip
            "atras": (0.0, 0.0),
            "izquierda": (0.0, np.pi / 2),
            "derecha": (0.0, -np.pi / 2),
            "arriba": (np.pi / 2, 0.0),
            "abajo": (-np.pi / 2, 0.0),
        }
        if name in FACES:
            pitch, yaw = FACES[name]
            qy = Quaternion.from_y_rotation(yaw)
            qx = Quaternion.from_x_rotation(pitch)
            self.model_quat = qy * qx
