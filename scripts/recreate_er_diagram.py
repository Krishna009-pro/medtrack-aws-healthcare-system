import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
import os

# Create high-resolution figure (16x10 inches at 300 DPI = 4800x3000 px)
fig, ax = plt.subplots(figsize=(16, 10), dpi=300)
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis('off')
fig.patch.set_facecolor('#ffffff')
ax.set_facecolor('#ffffff')

# Color palette: Elegant, modern, professional healthcare tech
BORDER_COLOR = '#1e293b'      # Dark slate
HEADER_BG = '#0f172a'         # Deep navy slate
BODY_BG = '#ffffff'           # Pure white
TEXT_HEADER = '#ffffff'       # White text
TEXT_ATTR = '#334155'         # Slate 700 text
ARROW_COLOR = '#0f172a'       # Solid dark slate
BADGE_BG = '#f1f5f9'          # Subtle light slate background for badges
BADGE_BORDER = '#94a3b8'
BADGE_TEXT = '#0f172a'

def draw_entity_box(ax, x_center, y_center, width, height, title, attributes, pk_fk_info=None):
    """Draws a professional entity box with header, attributes, and clean typography."""
    x0 = x_center - width / 2
    y0 = y_center - height / 2
    
    # Outer Card
    outer_box = FancyBboxPatch(
        (x0, y0), width, height,
        boxstyle="round,pad=0.2,rounding_size=0.8",
        ec=BORDER_COLOR, fc=BODY_BG, lw=2.2, zorder=2
    )
    ax.add_patch(outer_box)
    
    # Header bar
    header_height = height * 0.45
    header_y0 = y0 + height - header_height
    header_box = FancyBboxPatch(
        (x0, header_y0), width, header_height,
        boxstyle="round,pad=0.2,rounding_size=0.8",
        ec=BORDER_COLOR, fc=HEADER_BG, lw=2.2, zorder=3
    )
    ax.add_patch(header_box)
    
    # Overlap rectangle to square off the bottom of the header
    header_rect = patches.Rectangle(
        (x0 + 0.1, header_y0), width - 0.2, header_height * 0.4,
        fc=HEADER_BG, ec=HEADER_BG, lw=0, zorder=3.5
    )
    ax.add_patch(header_rect)
    
    # Header separator line
    ax.plot([x0, x0 + width], [header_y0, header_y0], color=BORDER_COLOR, lw=2.0, zorder=4)
    
    # Title Text
    ax.text(
        x_center, header_y0 + header_height / 2, title,
        ha='center', va='center', fontsize=16, fontweight='bold',
        color=TEXT_HEADER, zorder=5, fontfamily='DejaVu Sans'
    )
    
    # Attributes Text
    attr_y = y0 + (height - header_height) / 2
    ax.text(
        x_center, attr_y, attributes,
        ha='center', va='center', fontsize=11.5, fontweight='medium',
        color=TEXT_ATTR, zorder=5, fontfamily='DejaVu Sans'
    )

def draw_arrow(ax, start, end, label, label_pos=0.5, label_offset=(0, 0)):
    """Draws a clean directed arrow with cardinality label badge."""
    # Arrow line
    arrow = FancyArrowPatch(
        start, end,
        arrowstyle="-|>,head_length=8,head_width=5",
        connectionstyle="arc3,rad=0",
        color=ARROW_COLOR, lw=2.0, zorder=1
    )
    ax.add_patch(arrow)
    
    # Label position
    lx = start[0] + (end[0] - start[0]) * label_pos + label_offset[0]
    ly = start[1] + (end[1] - start[1]) * label_pos + label_offset[1]
    
    # Badge background
    ax.text(
        lx, ly, f"  {label}  ",
        ha='center', va='center', fontsize=12, fontweight='bold',
        color='#0f172a', zorder=6, fontfamily='DejaVu Sans',
        bbox=dict(boxstyle="round,pad=0.25", fc='#ffffff', ec='#64748b', lw=1.2)
    )

# --- Entity Definitions ---

# Row 1: Users (Centered at top)
users_x, users_y = 50, 88
users_w, users_h = 42, 10
draw_entity_box(
    ax, users_x, users_y, users_w, users_h,
    "Users",
    "(UserID, Name, Email, Role, Password, Phone)"
)

# Row 2: Doctors, Patients, Notifications
doc_x, doc_y = 19, 64
doc_w, doc_h = 32, 10
draw_entity_box(
    ax, doc_x, doc_y, doc_w, doc_h,
    "Doctors",
    "(DoctorID, UserID, Specialization, Experience)"
)

pat_x, pat_y = 50, 64
pat_w, pat_h = 28, 10
draw_entity_box(
    ax, pat_x, pat_y, pat_w, pat_h,
    "Patients",
    "(PatientID, UserID, Age, MedicalHistory)"
)

notif_x, notif_y = 81, 64
notif_w, notif_h = 30, 10
draw_entity_box(
    ax, notif_x, notif_y, notif_w, notif_h,
    "Notifications",
    "(NotificationID, UserID, Message, Timestamp)"
)

# Row 3: Appointments (Centered under Doctors and Patients)
apt_x, apt_y = 34.5, 38
apt_w, apt_h = 44, 10
draw_entity_box(
    ax, apt_x, apt_y, apt_w, apt_h,
    "Appointments",
    "(AppointmentID, PatientID, DoctorID, Date, Time, Status)"
)

# Row 4: Diagnosis (Centered under Appointments)
diag_x, diag_y = 34.5, 12
diag_w, diag_h = 47, 10
draw_entity_box(
    ax, diag_x, diag_y, diag_w, diag_h,
    "Diagnosis",
    "(DiagnosisID, AppointmentID, DoctorID, PatientID, Report, Date)"
)

# --- Relationships & Arrows ---

# 1. Users to Doctors (1:N)
draw_arrow(
    ax,
    start=(users_x - 12, users_y - users_h / 2),
    end=(doc_x + 5, doc_y + doc_h / 2),
    label="1:N", label_pos=0.5, label_offset=(-1.5, 0.5)
)

# 2. Users to Patients (1:N)
draw_arrow(
    ax,
    start=(users_x, users_y - users_h / 2),
    end=(pat_x, pat_y + pat_h / 2),
    label="1:N", label_pos=0.5, label_offset=(0, 0)
)

# 3. Users to Notifications (1:N)
draw_arrow(
    ax,
    start=(users_x + 12, users_y - users_h / 2),
    end=(notif_x - 5, notif_y + notif_h / 2),
    label="1:N", label_pos=0.5, label_offset=(1.5, 0.5)
)

# 4. Doctors to Appointments (1:N)
draw_arrow(
    ax,
    start=(doc_x + 6, doc_y - doc_h / 2),
    end=(apt_x - 11, apt_y + apt_h / 2),
    label="1:N", label_pos=0.48, label_offset=(-1.5, 0.5)
)

# 5. Patients to Appointments (1:N)
draw_arrow(
    ax,
    start=(pat_x - 6, pat_y - pat_h / 2),
    end=(apt_x + 11, apt_y + apt_h / 2),
    label="1:N", label_pos=0.48, label_offset=(1.5, 0.5)
)

# 6. Appointments to Diagnosis (1:1)
draw_arrow(
    ax,
    start=(apt_x, apt_y - apt_h / 2),
    end=(diag_x, diag_y + diag_h / 2),
    label="1:1", label_pos=0.5, label_offset=(0, 0)
)

plt.tight_layout()

# Save to destination path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out_path = os.path.join(base_dir, "images", "er_diagram.png")

os.makedirs(os.path.dirname(out_path), exist_ok=True)
fig.savefig(out_path, dpi=300, bbox_inches='tight', pad_inches=0.4)
plt.close(fig)

print(f"Generated high-resolution ER diagram at: {out_path}")
