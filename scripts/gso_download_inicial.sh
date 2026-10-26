#!/bin/bash
# Baixa o subconjunto de avaliacao do Google Scanned Objects (CC-BY 4.0) via Gazebo Fuel (owner GoogleResearch)
set -e
D=~/cerise2026/gen3d/data/gso
mkdir -p $D && cd $D
OBJS="Schleich_Bald_Eagle Schleich_African_Black_Rhino Sonny_School_Bus Threshold_Porcelain_Teapot_White \
Crosley_Alarm_Clock_Vintage_Metal Android_Figure_Panda ACE_Coffee_Mug_Kristen_16_oz_cup Great_Dinos_Triceratops_Toy \
Breyer_Horse_Of_The_Year_2015 Reebok_ZIGLITE_RUSH Vtech_Roll_Learn_Turtle Lovable_Huggable_Cuddly_Boutique_Teddy_Bear_Beige \
Transformers_Age_of_Extinction_Mega_1Step_Bumblebee_Figure"
for o in $OBJS; do
  if [ ! -f "$o/meshes/model.obj" ]; then
    curl -s -L -o "$o.zip" "https://fuel.gazebosim.org/1.0/GoogleResearch/models/$o.zip"
    mkdir -p "$o" && (cd "$o" && unzip -q -o "../$o.zip") && rm -f "$o.zip"
  fi
  echo "$o: $(ls $o/meshes 2>/dev/null | tr '\n' ' ') | $(ls $o/materials/textures 2>/dev/null | tr '\n' ' ')"
done
du -sh $D
