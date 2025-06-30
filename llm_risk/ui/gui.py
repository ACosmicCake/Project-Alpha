def _draw_world_map_polygons(self, game_state: GameState):
        gs_to_draw = game_state
        if not gs_to_draw: gs_to_draw = getattr(self, 'current_game_state', self.engine.game_state)

        map_area_rect = pygame.Rect(0, 0, MAP_AREA_WIDTH, SCREEN_HEIGHT)
        self.screen.fill(self.ocean_color, map_area_rect) # Ensure map area is cleared

        if not gs_to_draw or not gs_to_draw.territories:
            no_map_text = self.large_font.render("World Map Data Unavailable", True, WHITE)
            self.screen.blit(no_map_text, no_map_text.get_rect(center=map_area_rect.center))
            return

        if not self.territory_polygons:
            # This case means no polygon data was loaded at all.
            # Adjacency lines and text might still draw if centroids exist.
            # Consider logging a warning once if this happens during a game session.
            pass

        # Adjacency lines for world map
        drawn_adjacencies = set()
        for terr_name_adj, territory_obj_adj in gs_to_draw.territories.items():
            coords1 = self.territory_coordinates.get(terr_name_adj)
            if not coords1: continue
            for adj_territory_object in territory_obj_adj.adjacent_territories:
                adj_name = adj_territory_object.name
                adj_pair = tuple(sorted((terr_name_adj, adj_name)))
                if adj_pair in drawn_adjacencies: continue
                coords2 = self.territory_coordinates.get(adj_name)
                if not coords2: continue
                pygame.draw.line(self.screen, ADJACENCY_LINE_COLOR, coords1, coords2, 1)
                drawn_adjacencies.add(adj_pair)

        # Draw polygons
        for terr_name, territory_obj in gs_to_draw.territories.items():
            list_of_screen_polygon_points = self.territory_polygons.get(terr_name)
            screen_centroid_coords = self.territory_coordinates.get(terr_name)

            owner_color = DEFAULT_PLAYER_COLORS.get(territory_obj.owner.color, GREY) if territory_obj.owner and territory_obj.owner.color else GREY

            if list_of_screen_polygon_points:
                for i, screen_polygon_part_points in enumerate(list_of_screen_polygon_points):
                    if screen_polygon_part_points and len(screen_polygon_part_points) >= 3:
                        try:
                            pygame.draw.polygon(self.screen, owner_color, screen_polygon_part_points)
                            pygame.draw.polygon(self.screen, BLACK, screen_polygon_part_points, 1) # Border
                        except TypeError as e:
                            print(f"Error drawing polygon part {i} for {terr_name}: {e}. Screen points: {screen_polygon_part_points}")
                            if screen_centroid_coords:
                                pygame.draw.circle(self.screen, owner_color, screen_centroid_coords, 5, 0)
            elif screen_centroid_coords:
                pygame.draw.circle(self.screen, owner_color, screen_centroid_coords, 10)
                pygame.draw.circle(self.screen, BLACK, screen_centroid_coords, 10, 1)

            if screen_centroid_coords:
                army_text_color = BLACK if sum(owner_color) / 3 > 128 else WHITE
                army_text = self.font.render(str(territory_obj.army_count), True, army_text_color)

                army_text_rect = army_text.get_rect(center=screen_centroid_coords)
                army_bg_rect = army_text_rect.inflate(4,2)
                pygame.draw.rect(self.screen, owner_color, army_bg_rect, border_radius=3)
                pygame.draw.rect(self.screen, BLACK, army_bg_rect, 1, border_radius=3)
                self.screen.blit(army_text, army_text_rect)

                name_surf = self.font.render(terr_name, True, WHITE)
                name_rect = name_surf.get_rect(center=(screen_centroid_coords[0], screen_centroid_coords[1] + 15)) # Offset below
                name_bg_rect = name_rect.inflate(4,2)
                pygame.draw.rect(self.screen, DARK_GREY, name_bg_rect, border_radius=3)
                self.screen.blit(name_surf, name_rect)
