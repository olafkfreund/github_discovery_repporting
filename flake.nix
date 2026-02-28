{
  description = "DevOps Discovery & Reporting Platform";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            # Python
            python312
            uv

            # WeasyPrint system deps
            pango
            cairo
            gdk-pixbuf
            gobject-introspection
            libffi
            zlib
            fontconfig
            freetype
            harfbuzz

            # Node.js for frontend
            nodejs_22
            nodePackages.npm

            # Database tools
            postgresql_17

            # Dev tools
            just
            jq
            curl
          ];

          shellHook = ''
            echo "DevOps Discovery dev shell loaded"
            export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath [
              pkgs.pango
              pkgs.cairo
              pkgs.gdk-pixbuf
              pkgs.gobject-introspection
              pkgs.libffi
              pkgs.zlib
              pkgs.fontconfig
              pkgs.freetype
              pkgs.harfbuzz
            ]}:$LD_LIBRARY_PATH"
          '';
        };
      });
}
