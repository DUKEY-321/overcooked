using System;
using System.Collections.Generic;
using System.Globalization;
using BepInEx;
using BepInEx.Configuration;
using OC2DIYChefTrailColor;
using UnityEngine;

namespace OC2DIYChefTrailColorGUI
{
    [BepInPlugin(PluginGuid, PluginName, PluginVersion)]
    [BepInDependency(TrailColorPlugin.PluginGuid, BepInDependency.DependencyFlags.HardDependency)]
    [BepInProcess("Overcooked2.exe")]
    public sealed class TrailColorGuiPlugin : BaseUnityPlugin
    {
        public const string PluginGuid = "local.oc2.diycheftrailcolorgui";
        public const string PluginName = "OC2 DIY Chef Trail Color GUI";
        public const string PluginVersion = "0.2.0";

        private const int WindowId = 17425;
        private const int PaletteTextureSize = 128;
        private const int HueTextureHeight = 256;
        private const float DefaultWindowWidth = 980f;
        private const float DefaultWindowHeight = 620f;
        private const float SidebarWidth = 250f;

        private enum ProfileFilter
        {
            All,
            Diy,
            Official
        }

        private ConfigEntry<KeyboardShortcut> toggleShortcut;
        private Rect windowRect = new Rect(
            40f,
            40f,
            DefaultWindowWidth,
            DefaultWindowHeight);
        private bool visible;
        private bool dirty;
        private bool editDash;
        private bool previousCursorVisible;
        private CursorLockMode previousCursorLockMode;

        private TrailColorProfile selectedProfile;
        private string selectedStableKey;
        private string profileSearchText = string.Empty;
        private ProfileFilter profileFilter = ProfileFilter.All;
        private Vector2 profileScrollPosition;
        private Color workingColor = Color.white;
        private float hue;
        private float saturation;
        private float value = 1f;
        private string hexText = "FFFFFF";
        private Texture2D hueTexture;
        private Texture2D paletteTexture;
        private Texture2D whiteTexture;
        private float paletteHue = -1f;

        private void Awake()
        {
            Config.SaveOnConfigSet = false;
            toggleShortcut = Config.Bind(
                "GUI",
                "ToggleShortcut",
                new KeyboardShortcut(KeyCode.F10),
                "Open or close the character trail-colour palette.");
            Config.Save();
            BuildHueTexture();
            BuildWhiteTexture();
            SelectFirstProfile();
            Logger.LogInfo("Palette ready. Press F10 to open the character trail-colour GUI.");
        }

        private void Update()
        {
            if (toggleShortcut.Value.IsDown())
            {
                SetVisible(!visible);
            }
            else if (visible && Input.GetKeyDown(KeyCode.Escape))
            {
                SetVisible(false);
            }

            if (visible)
            {
                Input.ResetInputAxes();
            }
        }

        private void OnGUI()
        {
            if (!visible)
            {
                return;
            }

            ClampWindowToScreen();
            windowRect = GUI.Window(WindowId, windowRect, DrawWindow, "OC2 DIY Chef Trail Color");
        }

        private void OnDestroy()
        {
            if (visible)
            {
                RestoreCursor();
            }
            SaveIfDirty();
            DestroyTexture(ref hueTexture);
            DestroyTexture(ref paletteTexture);
            DestroyTexture(ref whiteTexture);
        }

        private void SelectFirstProfile()
        {
            TrailColorPlugin core = TrailColorPlugin.Instance;
            if (core == null)
            {
                return;
            }

            SynchronizeSelectedProfile(core.Profiles);
        }

        private void SetVisible(bool nextVisible)
        {
            if (visible == nextVisible)
            {
                return;
            }

            visible = nextVisible;
            if (visible)
            {
                previousCursorVisible = Cursor.visible;
                previousCursorLockMode = Cursor.lockState;
                Cursor.visible = true;
                Cursor.lockState = CursorLockMode.None;
                TrailColorPlugin core = TrailColorPlugin.Instance;
                if (core != null)
                {
                    SynchronizeSelectedProfile(core.Profiles);
                }
                if (selectedProfile != null)
                {
                    LoadWorkingColor();
                }
            }
            else
            {
                SaveIfDirty();
                RestoreCursor();
            }
        }

        private void RestoreCursor()
        {
            Cursor.visible = previousCursorVisible;
            Cursor.lockState = previousCursorLockMode;
        }

        private void DrawWindow(int windowId)
        {
            TrailColorPlugin core = TrailColorPlugin.Instance;
            if (core == null)
            {
                GUILayout.Label("Core plugin is not available / 核心插件未加载");
                if (GUILayout.Button("Close / 关闭"))
                {
                    SetVisible(false);
                }
                GUI.DragWindow(new Rect(0f, 0f, windowRect.width, 28f));
                return;
            }

            IList<TrailColorProfile> profiles = core.Profiles;
            SynchronizeSelectedProfile(profiles);

            GUILayout.BeginHorizontal();
            DrawProfileSelector(profiles);
            GUILayout.Space(12f);
            GUILayout.BeginVertical(GUILayout.ExpandWidth(true), GUILayout.ExpandHeight(true));

            if (selectedProfile == null)
            {
                GUILayout.Label("No character colour profile is configured.");
            }
            else
            {
                DrawSelectedProfileEditor();
            }

            GUILayout.EndVertical();
            GUILayout.EndHorizontal();
            GUI.DragWindow(new Rect(0f, 0f, windowRect.width, 28f));
        }

        private void DrawSelectedProfileEditor()
        {
            GUILayout.Label(selectedProfile.DisplayName + "  [" + selectedProfile.StableKey + "]");

            bool enabled = GUILayout.Toggle(
                selectedProfile.Enabled,
                "Enable character colour / 启用角色尾气颜色");
            if (enabled != selectedProfile.Enabled)
            {
                selectedProfile.Enabled = enabled;
                dirty = true;
            }

            GUILayout.BeginHorizontal();
            if (DrawModeButton(!editDash, "Running Smoke / 走路烟雾"))
            {
                editDash = false;
                LoadWorkingColor();
            }
            if (DrawModeButton(editDash, "Dash Trail / 冲刺尾气"))
            {
                editDash = true;
                LoadWorkingColor();
            }
            GUILayout.EndHorizontal();

            GUILayout.Space(4f);
            GUILayout.BeginHorizontal();
            DrawPalette();
            GUILayout.Space(14f);
            DrawNumericControls();
            GUILayout.EndHorizontal();

            GUILayout.FlexibleSpace();
            GUILayout.BeginHorizontal();
            if (GUILayout.Button("Reset current / 重置当前", GUILayout.Height(30f)))
            {
                selectedProfile.Enabled = true;
                if (editDash)
                {
                    selectedProfile.DashColor = selectedProfile.DefaultDashColor;
                }
                else
                {
                    selectedProfile.WalkColor = selectedProfile.DefaultWalkColor;
                }
                dirty = true;
                LoadWorkingColor();
            }
            if (GUILayout.Button("Save / 保存", GUILayout.Height(30f)))
            {
                SaveIfDirty();
            }
            if (GUILayout.Button("Close / 关闭 (F10)", GUILayout.Height(30f)))
            {
                SetVisible(false);
            }
            GUILayout.EndHorizontal();
        }

        private void DrawProfileSelector(IList<TrailColorProfile> profiles)
        {
            List<TrailColorProfile> filteredProfiles = new List<TrailColorProfile>();
            for (int index = 0; index < profiles.Count; index++)
            {
                TrailColorProfile profile = profiles[index];
                if (ProfileMatchesFilter(profile) && ProfileMatchesSearch(profile))
                {
                    filteredProfiles.Add(profile);
                }
            }
            filteredProfiles.Sort(CompareProfiles);

            GUILayout.BeginVertical(
                GUI.skin.box,
                GUILayout.Width(SidebarWidth),
            GUILayout.ExpandHeight(true));
            GUILayout.Label("Characters / 角色  " + filteredProfiles.Count + "/" + profiles.Count);

            GUILayout.Label("Search / 搜索");
            profileSearchText = GUILayout.TextField(
                profileSearchText ?? string.Empty,
                GUILayout.Width(SidebarWidth - 16f));

            GUILayout.BeginHorizontal();
            DrawProfileFilterButton(ProfileFilter.All, "全部");
            DrawProfileFilterButton(ProfileFilter.Diy, "DIY");
            DrawProfileFilterButton(ProfileFilter.Official, "官方");
            GUILayout.EndHorizontal();

            GUILayout.Space(4f);
            profileScrollPosition = GUILayout.BeginScrollView(
                profileScrollPosition,
                false,
                true,
                GUILayout.ExpandHeight(true));

            if (filteredProfiles.Count == 0)
            {
                GUILayout.Label("No matching characters.\n没有匹配的角色。");
            }

            for (int index = 0; index < filteredProfiles.Count; index++)
            {
                TrailColorProfile profile = filteredProfiles[index];
                bool selected = string.Equals(
                    profile.StableKey,
                    selectedStableKey,
                    StringComparison.Ordinal);
                Color oldBackground = GUI.backgroundColor;
                if (selected)
                {
                    GUI.backgroundColor = new Color(1f, 0.72f, 0.86f, 1f);
                }
                if (GUILayout.Button(
                    BuildProfileLabel(profile),
                    GUILayout.Height(46f),
                    GUILayout.ExpandWidth(true)))
                {
                    SelectProfile(profile);
                }
                GUI.backgroundColor = oldBackground;
            }

            GUILayout.EndScrollView();
            GUILayout.EndVertical();
        }

        private void DrawProfileFilterButton(ProfileFilter filter, string label)
        {
            Color oldBackground = GUI.backgroundColor;
            if (profileFilter == filter)
            {
                GUI.backgroundColor = new Color(1f, 0.72f, 0.86f, 1f);
            }
            if (GUILayout.Button(label, GUILayout.Height(26f)))
            {
                profileFilter = filter;
                profileScrollPosition = Vector2.zero;
            }
            GUI.backgroundColor = oldBackground;
        }

        private bool ProfileMatchesFilter(TrailColorProfile profile)
        {
            if (profileFilter == ProfileFilter.Diy)
            {
                return profile.IsDiy;
            }
            if (profileFilter == ProfileFilter.Official)
            {
                return !profile.IsDiy;
            }
            return true;
        }

        private bool ProfileMatchesSearch(TrailColorProfile profile)
        {
            string search = (profileSearchText ?? string.Empty).Trim();
            if (search.Length == 0)
            {
                return true;
            }

            return ContainsIgnoreCase(profile.DisplayName, search) ||
                   ContainsIgnoreCase(profile.StableKey, search) ||
                   ContainsIgnoreCase(profile.HeadName, search) ||
                   ContainsIgnoreCase(
                       Convert.ToString(profile.DiyId, CultureInfo.InvariantCulture),
                       search);
        }

        private static bool ContainsIgnoreCase(string value, string search)
        {
            return !string.IsNullOrEmpty(value) &&
                   value.IndexOf(search, StringComparison.OrdinalIgnoreCase) >= 0;
        }

        private static int CompareProfiles(TrailColorProfile left, TrailColorProfile right)
        {
            if (left.IsDiy != right.IsDiy)
            {
                return left.IsDiy ? -1 : 1;
            }

            return string.Compare(
                left.DisplayName,
                right.DisplayName,
                StringComparison.OrdinalIgnoreCase);
        }

        private static string BuildProfileLabel(TrailColorProfile profile)
        {
            string displayName = string.IsNullOrEmpty(profile.DisplayName)
                ? profile.StableKey
                : profile.DisplayName;
            string typeLabel = profile.IsDiy
                ? "DIY #" + Convert.ToString(profile.DiyId, CultureInfo.InvariantCulture)
                : "官方 / Official";
            string identity = string.IsNullOrEmpty(profile.HeadName)
                ? profile.StableKey
                : profile.HeadName;
            return displayName + "\n" + typeLabel + " · " + identity;
        }

        private static bool DrawModeButton(bool selected, string label)
        {
            Color oldBackground = GUI.backgroundColor;
            if (selected)
            {
                GUI.backgroundColor = new Color(1f, 0.58f, 0.76f, 1f);
            }
            bool pressed = GUILayout.Button(label, GUILayout.Height(30f));
            GUI.backgroundColor = oldBackground;
            return pressed;
        }

        private void DrawPalette()
        {
            GUILayout.BeginVertical(GUILayout.Width(390f));
            GUILayout.Label("HSV Palette / 调色盘");
            GUILayout.BeginHorizontal();

            Rect paletteRect = GUILayoutUtility.GetRect(
                330f,
                330f,
                GUILayout.Width(330f),
                GUILayout.Height(330f));
            EnsurePaletteTexture();
            GUI.DrawTexture(paletteRect, paletteTexture, ScaleMode.StretchToFill, false);
            HandlePaletteInput(paletteRect);
            DrawPaletteMarker(paletteRect);

            Rect hueRect = GUILayoutUtility.GetRect(
                28f,
                330f,
                GUILayout.Width(28f),
                GUILayout.Height(330f));
            GUI.DrawTexture(hueRect, hueTexture, ScaleMode.StretchToFill, false);
            HandleHueInput(hueRect);
            DrawHueMarker(hueRect);

            GUILayout.EndHorizontal();
            GUILayout.EndVertical();
        }

        private void DrawNumericControls()
        {
            GUILayout.BeginVertical(GUILayout.Width(240f));
            GUILayout.Label(editDash ? "Dash colour / 冲刺颜色" : "Walk colour / 走路颜色");

            Color oldColor = GUI.color;
            GUI.color = workingColor;
            GUILayout.Box(whiteTexture, GUILayout.Width(220f), GUILayout.Height(62f));
            GUI.color = oldColor;

            GUILayout.Label("HEX (RRGGBB)");
            hexText = GUILayout.TextField(hexText, 6, GUILayout.Width(220f));
            if (GUILayout.Button("Apply HEX / 应用", GUILayout.Width(220f)))
            {
                Color parsed;
                if (TryParseHexColor(hexText, out parsed))
                {
                    SetWorkingColor(parsed, true);
                }
            }

            GUILayout.Space(8f);
            DrawRgbSlider("R", workingColor.r, delegate(float component)
            {
                Color next = workingColor;
                next.r = component;
                return next;
            });
            DrawRgbSlider("G", workingColor.g, delegate(float component)
            {
                Color next = workingColor;
                next.g = component;
                return next;
            });
            DrawRgbSlider("B", workingColor.b, delegate(float component)
            {
                Color next = workingColor;
                next.b = component;
                return next;
            });

            GUILayout.Space(8f);
            GUILayout.Label("In-game shader may render colours lighter.");
            GUILayout.Label("游戏粒子材质可能使颜色变浅。 ");
            GUILayout.EndVertical();
        }

        private void DrawRgbSlider(
            string label,
            float current,
            Func<float, Color> updateColor)
        {
            GUILayout.BeginHorizontal();
            GUILayout.Label(label, GUILayout.Width(18f));
            float next = GUILayout.HorizontalSlider(current, 0f, 1f, GUILayout.Width(150f));
            GUILayout.Label(
                Mathf.RoundToInt(current * 255f).ToString(CultureInfo.InvariantCulture),
                GUILayout.Width(38f));
            GUILayout.EndHorizontal();
            if (Mathf.Abs(next - current) > 0.0001f)
            {
                SetWorkingColor(updateColor(next), true);
            }
        }

        private void HandlePaletteInput(Rect rect)
        {
            Event currentEvent = Event.current;
            if ((currentEvent.type == EventType.MouseDown ||
                 currentEvent.type == EventType.MouseDrag) &&
                currentEvent.button == 0 &&
                rect.Contains(currentEvent.mousePosition))
            {
                saturation = Mathf.Clamp01((currentEvent.mousePosition.x - rect.x) / rect.width);
                value = 1f - Mathf.Clamp01((currentEvent.mousePosition.y - rect.y) / rect.height);
                SetWorkingColor(Color.HSVToRGB(hue, saturation, value), true);
                currentEvent.Use();
            }
        }

        private void HandleHueInput(Rect rect)
        {
            Event currentEvent = Event.current;
            if ((currentEvent.type == EventType.MouseDown ||
                 currentEvent.type == EventType.MouseDrag) &&
                currentEvent.button == 0 &&
                rect.Contains(currentEvent.mousePosition))
            {
                hue = Mathf.Clamp01((currentEvent.mousePosition.y - rect.y) / rect.height);
                paletteHue = -1f;
                SetWorkingColor(Color.HSVToRGB(hue, saturation, value), true);
                currentEvent.Use();
            }
        }

        private void DrawPaletteMarker(Rect rect)
        {
            float x = rect.x + saturation * rect.width;
            float y = rect.y + (1f - value) * rect.height;
            GUI.Box(new Rect(x - 5f, y - 5f, 10f, 10f), string.Empty);
        }

        private void DrawHueMarker(Rect rect)
        {
            float y = rect.y + hue * rect.height;
            GUI.Box(new Rect(rect.x - 3f, y - 3f, rect.width + 6f, 6f), string.Empty);
        }

        private void SynchronizeSelectedProfile(IList<TrailColorProfile> profiles)
        {
            TrailColorProfile matchedProfile = null;
            if (!string.IsNullOrEmpty(selectedStableKey))
            {
                for (int index = 0; index < profiles.Count; index++)
                {
                    TrailColorProfile profile = profiles[index];
                    if (string.Equals(
                            profile.StableKey,
                            selectedStableKey,
                            StringComparison.Ordinal))
                    {
                        matchedProfile = profile;
                        break;
                    }
                }
            }

            if (matchedProfile != null)
            {
                if (!ReferenceEquals(selectedProfile, matchedProfile))
                {
                    selectedProfile = matchedProfile;
                    LoadWorkingColor();
                }
                return;
            }

            selectedProfile = null;
            selectedStableKey = null;
            if (profiles.Count > 0)
            {
                SelectProfile(profiles[0]);
            }
        }

        private void SelectProfile(TrailColorProfile profile)
        {
            selectedProfile = profile;
            selectedStableKey = profile == null ? null : profile.StableKey;
            editDash = false;
            LoadWorkingColor();
        }

        private void LoadWorkingColor()
        {
            if (selectedProfile == null)
            {
                return;
            }

            Color next = editDash ? selectedProfile.DashColor : selectedProfile.WalkColor;
            SetWorkingColor(next, false);
        }

        private void SetWorkingColor(Color color, bool updateProfile)
        {
            color.a = 1f;
            workingColor = color;
            Color.RGBToHSV(workingColor, out hue, out saturation, out value);
            paletteHue = -1f;
            hexText = ColorUtility.ToHtmlStringRGB(workingColor);

            if (updateProfile && selectedProfile != null)
            {
                if (!selectedProfile.Enabled)
                {
                    selectedProfile.Enabled = true;
                }
                if (editDash)
                {
                    selectedProfile.DashColor = workingColor;
                }
                else
                {
                    selectedProfile.WalkColor = workingColor;
                }
                dirty = true;
            }
        }

        private void SaveIfDirty()
        {
            if (!dirty)
            {
                return;
            }

            TrailColorPlugin core = TrailColorPlugin.Instance;
            if (core != null)
            {
                core.SaveConfiguration();
            }
            Config.Save();
            dirty = false;
            Logger.LogInfo("Saved character trail-colour palette settings.");
        }

        private void BuildHueTexture()
        {
            hueTexture = new Texture2D(8, HueTextureHeight, TextureFormat.RGB24, false);
            hueTexture.wrapMode = TextureWrapMode.Clamp;
            hueTexture.filterMode = FilterMode.Bilinear;
            Color[] pixels = new Color[8 * HueTextureHeight];
            for (int y = 0; y < HueTextureHeight; y++)
            {
                Color row = Color.HSVToRGB(
                    1f - (float)y / (HueTextureHeight - 1),
                    1f,
                    1f);
                for (int x = 0; x < 8; x++)
                {
                    pixels[y * 8 + x] = row;
                }
            }
            hueTexture.SetPixels(pixels);
            hueTexture.Apply(false, true);
        }

        private void EnsurePaletteTexture()
        {
            if (paletteTexture != null && Mathf.Abs(paletteHue - hue) < 0.001f)
            {
                return;
            }

            if (paletteTexture == null)
            {
                paletteTexture = new Texture2D(
                    PaletteTextureSize,
                    PaletteTextureSize,
                    TextureFormat.RGB24,
                    false);
                paletteTexture.wrapMode = TextureWrapMode.Clamp;
                paletteTexture.filterMode = FilterMode.Bilinear;
            }

            Color[] pixels = new Color[PaletteTextureSize * PaletteTextureSize];
            for (int y = 0; y < PaletteTextureSize; y++)
            {
                float pixelValue = (float)y / (PaletteTextureSize - 1);
                for (int x = 0; x < PaletteTextureSize; x++)
                {
                    float pixelSaturation = (float)x / (PaletteTextureSize - 1);
                    pixels[y * PaletteTextureSize + x] =
                        Color.HSVToRGB(hue, pixelSaturation, pixelValue);
                }
            }
            paletteTexture.SetPixels(pixels);
            paletteTexture.Apply(false, false);
            paletteHue = hue;
        }

        private void BuildWhiteTexture()
        {
            whiteTexture = new Texture2D(1, 1, TextureFormat.RGB24, false);
            whiteTexture.SetPixel(0, 0, Color.white);
            whiteTexture.Apply(false, true);
        }

        private static bool TryParseHexColor(string text, out Color color)
        {
            color = Color.white;
            if (string.IsNullOrEmpty(text))
            {
                return false;
            }

            string normalized = text.Trim().TrimStart('#');
            if (normalized.Length != 6)
            {
                return false;
            }

            int red;
            int green;
            int blue;
            if (!int.TryParse(
                    normalized.Substring(0, 2),
                    NumberStyles.HexNumber,
                    CultureInfo.InvariantCulture,
                    out red) ||
                !int.TryParse(
                    normalized.Substring(2, 2),
                    NumberStyles.HexNumber,
                    CultureInfo.InvariantCulture,
                    out green) ||
                !int.TryParse(
                    normalized.Substring(4, 2),
                    NumberStyles.HexNumber,
                    CultureInfo.InvariantCulture,
                    out blue))
            {
                return false;
            }

            color = new Color(red / 255f, green / 255f, blue / 255f, 1f);
            return true;
        }

        private void ClampWindowToScreen()
        {
            windowRect.width = Mathf.Min(
                DefaultWindowWidth,
                Mathf.Max(320f, Screen.width - 20f));
            windowRect.height = Mathf.Min(
                DefaultWindowHeight,
                Mathf.Max(240f, Screen.height - 20f));
            float maxX = Mathf.Max(0f, Screen.width - windowRect.width);
            float maxY = Mathf.Max(0f, Screen.height - windowRect.height);
            windowRect.x = Mathf.Clamp(windowRect.x, 0f, maxX);
            windowRect.y = Mathf.Clamp(windowRect.y, 0f, maxY);
        }

        private static void DestroyTexture(ref Texture2D texture)
        {
            if (texture != null)
            {
                UnityEngine.Object.Destroy(texture);
                texture = null;
            }
        }
    }
}
