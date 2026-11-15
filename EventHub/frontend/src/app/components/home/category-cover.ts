import {
  BookOpen,
  Briefcase,
  CalendarDays,
  Drama,
  GraduationCap,
  Laptop,
  Music,
  Trophy,
  type LucideIconData,
} from 'lucide-angular';

export interface CategoryCover {
  icon: LucideIconData;
  /** CSS background for the cover (deep, so white text reads on it in both themes). */
  background: string;
}

/** Hue per seeded category icon (`music`, `laptop`, `briefcase`, `book`, `trophy`, `theater`). */
const COVERS: Record<string, { icon: LucideIconData; hue: number }> = {
  music: { icon: Music, hue: 22 },
  laptop: { icon: Laptop, hue: 178 },
  briefcase: { icon: Briefcase, hue: 212 },
  book: { icon: GraduationCap, hue: 232 },
  education: { icon: BookOpen, hue: 232 },
  trophy: { icon: Trophy, hue: 140 },
  theater: { icon: Drama, hue: 292 },
  theatre: { icon: Drama, hue: 292 },
};

/**
 * Fallback artwork for events without a photo: a deep gradient in the
 * category's hue with faint concentric rings, plus the category icon.
 * Unknown icons get a hue derived from the category id so rails still vary.
 */
export function categoryCover(icon: string | null | undefined, categoryId = 0): CategoryCover {
  const known = icon ? COVERS[icon.toLowerCase()] : undefined;
  const hue = known?.hue ?? (categoryId * 47) % 360;
  const rings =
    'repeating-radial-gradient(circle at 50% 46%, rgba(255,255,255,0.05) 0 1px, transparent 1px 34px)';
  const glow = `radial-gradient(120% 90% at 50% 40%, hsl(${hue} 42% 30%) 0%, hsl(${hue} 38% 16%) 60%, hsl(${hue} 30% 9%) 100%)`;
  return { icon: known?.icon ?? CalendarDays, background: `${rings}, ${glow}` };
}
