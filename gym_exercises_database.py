# ==================== DATABASE ESERCIZI PALESTRA ====================
# 40 esercizi completi con descrizioni dettagliate e immagini
# Ogni esercizio include: nome IT/EN, descrizione IT/EN, muscoli, attrezzatura, immagine

GYM_EXERCISES_DATABASE = {
    # ==================== PETTO ====================
    "panca-piana-bilanciere": {
        "name_it": "Panca Piana Bilanciere",
        "name_en": "Barbell Bench Press",
        "description_it": "Sdraiati sulla panca, impugna il bilanciere con presa leggermente più larga delle spalle. Abbassa il bilanciere fino al petto e spingi verso l'alto estendendo le braccia.",
        "description_en": "Lie on the bench, grip the barbell slightly wider than shoulder width. Lower the bar to your chest and push up by extending your arms.",
        "muscles_it": "Pettorali, tricipiti, deltoidi anteriori",
        "muscles_en": "Chest, triceps, front delts",
        "equipment": "bilanciere",
        "image": "panca-piana-bilanciere"
    },
    "panca-inclinata-manubri": {
        "name_it": "Panca Inclinata Manubri",
        "name_en": "Incline Dumbbell Press",
        "description_it": "Sdraiati sulla panca inclinata a 30-45°, tieni i manubri all'altezza del petto. Spingi verso l'alto estendendo le braccia, poi abbassa controllando il movimento.",
        "description_en": "Lie on an incline bench at 30-45°, hold dumbbells at chest level. Push up by extending your arms, then lower with control.",
        "muscles_it": "Pettorali alti, deltoidi anteriori, tricipiti",
        "muscles_en": "Upper chest, front delts, triceps",
        "equipment": "manubri",
        "image": "panca-inclinata-manubri"
    },
    "panca-inclinata-bilanciere": {
        "name_it": "Panca Inclinata Bilanciere",
        "name_en": "Incline Barbell Press",
        "description_it": "Sdraiati sulla panca inclinata, impugna il bilanciere. Abbassa fino alla parte alta del petto e spingi verso l'alto mantenendo i gomiti a 45°.",
        "description_en": "Lie on incline bench, grip the barbell. Lower to upper chest and push up keeping elbows at 45°.",
        "muscles_it": "Pettorali alti, tricipiti, deltoidi",
        "muscles_en": "Upper chest, triceps, delts",
        "equipment": "bilanciere",
        "image": "panca-piana-bilanciere"
    },
    "croci-manubri": {
        "name_it": "Croci con Manubri",
        "name_en": "Dumbbell Flyes",
        "description_it": "Sdraiati sulla panca piana con i manubri sopra il petto, braccia quasi tese. Apri le braccia lateralmente abbassando i pesi, poi riportali insieme stringendo i pettorali.",
        "description_en": "Lie on flat bench with dumbbells above chest, arms almost straight. Open arms laterally lowering weights, then bring back together squeezing chest.",
        "muscles_it": "Pettorali (isolamento)",
        "muscles_en": "Chest (isolation)",
        "equipment": "manubri",
        "image": "croci-manubri"
    },
    "croci-cavi": {
        "name_it": "Croci ai Cavi",
        "name_en": "Cable Crossover",
        "description_it": "In piedi tra due cavi alti, afferra le maniglie. Con le braccia leggermente piegate, porta le mani insieme davanti al petto contraendo i pettorali.",
        "description_en": "Stand between two high cables, grab handles. With slightly bent arms, bring hands together in front of chest contracting pecs.",
        "muscles_it": "Pettorali interni e bassi",
        "muscles_en": "Inner and lower chest",
        "equipment": "cavi",
        "image": "croci-cavi"
    },
    "panca-presa-stretta": {
        "name_it": "Panca Presa Stretta",
        "name_en": "Close Grip Bench Press",
        "description_it": "Sdraiati sulla panca, impugna il bilanciere con le mani alla larghezza delle spalle. Abbassa il bilanciere al petto e spingi su concentrandoti sui tricipiti.",
        "description_en": "Lie on bench, grip barbell at shoulder width. Lower bar to chest and push up focusing on triceps.",
        "muscles_it": "Tricipiti, pettorali interni",
        "muscles_en": "Triceps, inner chest",
        "equipment": "bilanciere",
        "image": "close-grip-bench"
    },

    # ==================== SCHIENA ====================
    "rematore-bilanciere": {
        "name_it": "Rematore con Bilanciere",
        "name_en": "Barbell Row",
        "description_it": "In piedi con busto inclinato a 45°, impugna il bilanciere. Tira il bilanciere verso l'addome stringendo le scapole, poi abbassa controllando.",
        "description_en": "Stand with torso at 45°, grip the barbell. Pull bar toward abdomen squeezing shoulder blades, then lower with control.",
        "muscles_it": "Dorsali, romboidi, bicipiti, trapezio",
        "muscles_en": "Lats, rhomboids, biceps, traps",
        "equipment": "bilanciere",
        "image": "rematore-bilanciere"
    },
    "rematore-manubrio": {
        "name_it": "Rematore con Manubrio",
        "name_en": "Dumbbell Row",
        "description_it": "Appoggia ginocchio e mano su una panca, schiena parallela al pavimento. Tira il manubrio verso l'anca stringendo il dorsale.",
        "description_en": "Place knee and hand on bench, back parallel to floor. Pull dumbbell toward hip squeezing your lat.",
        "muscles_it": "Dorsali, romboidi, bicipiti",
        "muscles_en": "Lats, rhomboids, biceps",
        "equipment": "manubri",
        "image": "rematore-manubrio"
    },
    "lat-machine": {
        "name_it": "Lat Machine",
        "name_en": "Lat Pulldown",
        "description_it": "Seduto alla lat machine, afferra la barra larga. Tira verso il petto portando i gomiti indietro, poi torna su lentamente.",
        "description_en": "Seated at lat machine, grab wide bar. Pull to chest bringing elbows back, then return slowly.",
        "muscles_it": "Dorsali, bicipiti, romboidi",
        "muscles_en": "Lats, biceps, rhomboids",
        "equipment": "macchina",
        "image": "lat-machine"
    },
    "trazioni-alla-sbarra": {
        "name_it": "Trazioni alla Sbarra",
        "name_en": "Pull-ups",
        "description_it": "Appeso alla sbarra con presa prona larga, tira il corpo verso l'alto portando il mento sopra la sbarra. Scendi controllando il movimento.",
        "description_en": "Hang from bar with wide overhand grip, pull body up bringing chin over bar. Lower with control.",
        "muscles_it": "Dorsali, bicipiti, core",
        "muscles_en": "Lats, biceps, core",
        "equipment": "sbarra",
        "image": "trazioni"
    },
    "t-bar-row": {
        "name_it": "T-Bar Row",
        "name_en": "T-Bar Row",
        "description_it": "In piedi sopra la barra a T, busto inclinato. Tira la barra verso il petto mantenendo la schiena dritta.",
        "description_en": "Stand over T-bar, torso bent forward. Pull bar toward chest keeping back straight.",
        "muscles_it": "Dorsali, romboidi, trapezio medio",
        "muscles_en": "Lats, rhomboids, mid traps",
        "equipment": "bilanciere",
        "image": "t-bar-row"
    },
    "pullover-manubrio": {
        "name_it": "Pullover con Manubrio",
        "name_en": "Dumbbell Pullover",
        "description_it": "Sdraiato trasversalmente sulla panca, tieni un manubrio sopra il petto. Porta il peso dietro la testa e riportalo sopra il petto.",
        "description_en": "Lie across bench, hold dumbbell above chest. Lower weight behind head and bring back above chest.",
        "muscles_it": "Dorsali, pettorali, tricipiti",
        "muscles_en": "Lats, chest, triceps",
        "equipment": "manubri",
        "image": "pullover-manubrio"
    },
    "rematore-cavi": {
        "name_it": "Rematore ai Cavi",
        "name_en": "Seated Cable Row",
        "description_it": "Seduto alla macchina, afferra la maniglia. Tira verso l'addome stringendo le scapole, poi estendi le braccia controllando.",
        "description_en": "Seated at machine, grab handle. Pull toward abdomen squeezing shoulder blades, then extend arms with control.",
        "muscles_it": "Dorsali, romboidi, bicipiti",
        "muscles_en": "Lats, rhomboids, biceps",
        "equipment": "cavi",
        "image": "rematore-cavi"
    },

    # ==================== GAMBE ====================
    "squat-bilanciere": {
        "name_it": "Squat con Bilanciere",
        "name_en": "Barbell Squat",
        "description_it": "Bilanciere appoggiato sui trapezi, piedi alla larghezza delle spalle. Scendi piegando le ginocchia fino ad avere le cosce parallele al pavimento, poi risali.",
        "description_en": "Barbell on traps, feet shoulder-width apart. Lower by bending knees until thighs are parallel to floor, then stand up.",
        "muscles_it": "Quadricipiti, glutei, femorali, core",
        "muscles_en": "Quads, glutes, hamstrings, core",
        "equipment": "bilanciere",
        "image": "squat-bilanciere"
    },
    "front-squat": {
        "name_it": "Front Squat",
        "name_en": "Front Squat",
        "description_it": "Bilanciere appoggiato sulle spalle anteriori, gomiti alti. Scendi mantenendo il busto eretto e risali spingendo sui talloni.",
        "description_en": "Barbell on front shoulders, elbows high. Lower keeping torso upright and stand up pushing through heels.",
        "muscles_it": "Quadricipiti, glutei, core",
        "muscles_en": "Quads, glutes, core",
        "equipment": "bilanciere",
        "image": "front-squat"
    },
    "squat-goblet": {
        "name_it": "Goblet Squat",
        "name_en": "Goblet Squat",
        "description_it": "Tieni un manubrio verticalmente davanti al petto. Scendi in squat mantenendo il peso vicino al corpo e il busto eretto.",
        "description_en": "Hold dumbbell vertically in front of chest. Lower into squat keeping weight close to body and torso upright.",
        "muscles_it": "Quadricipiti, glutei",
        "muscles_en": "Quads, glutes",
        "equipment": "manubri",
        "image": "squat-goblet"
    },
    "leg-press": {
        "name_it": "Leg Press",
        "name_en": "Leg Press",
        "description_it": "Seduto alla macchina, piedi sulla pedana alla larghezza delle spalle. Spingi la pedana estendendo le gambe, poi piega lentamente le ginocchia.",
        "description_en": "Seated at machine, feet on platform shoulder-width apart. Push platform by extending legs, then slowly bend knees.",
        "muscles_it": "Quadricipiti, glutei, femorali",
        "muscles_en": "Quads, glutes, hamstrings",
        "equipment": "macchina",
        "image": "leg-press"
    },
    "affondi-manubri": {
        "name_it": "Affondi con Manubri",
        "name_en": "Dumbbell Lunges",
        "description_it": "In piedi con un manubrio per mano, fai un passo avanti e piega entrambe le ginocchia a 90°. Spingi sul tallone anteriore per tornare in posizione.",
        "description_en": "Stand with dumbbell in each hand, step forward and bend both knees to 90°. Push through front heel to return.",
        "muscles_it": "Quadricipiti, glutei, femorali",
        "muscles_en": "Quads, glutes, hamstrings",
        "equipment": "manubri",
        "image": "affondi-manubri"
    },
    "split-squat-bulgaro": {
        "name_it": "Split Squat Bulgaro",
        "name_en": "Bulgarian Split Squat",
        "description_it": "Piede posteriore su una panca, manubri in mano. Scendi piegando il ginocchio anteriore a 90°, poi risali.",
        "description_en": "Back foot on bench, dumbbells in hands. Lower by bending front knee to 90°, then stand up.",
        "muscles_it": "Quadricipiti, glutei, equilibrio",
        "muscles_en": "Quads, glutes, balance",
        "equipment": "manubri",
        "image": "split-squat-bulgaro"
    },
    "leg-curl": {
        "name_it": "Leg Curl",
        "name_en": "Leg Curl",
        "description_it": "Sdraiato a pancia in giù sulla macchina, porta i talloni verso i glutei piegando le ginocchia. Abbassa lentamente.",
        "description_en": "Lying face down on machine, bring heels toward glutes by bending knees. Lower slowly.",
        "muscles_it": "Femorali (bicipite femorale)",
        "muscles_en": "Hamstrings",
        "equipment": "macchina",
        "image": "leg-curl"
    },
    "leg-extension": {
        "name_it": "Leg Extension",
        "name_en": "Leg Extension",
        "description_it": "Seduto alla macchina, estendi le gambe sollevando il peso. Contrai i quadricipiti in alto, poi abbassa lentamente.",
        "description_en": "Seated at machine, extend legs lifting weight. Contract quads at top, then lower slowly.",
        "muscles_it": "Quadricipiti (isolamento)",
        "muscles_en": "Quads (isolation)",
        "equipment": "macchina",
        "image": "leg-extension"
    },
    "calf-raises-manubri": {
        "name_it": "Calf Raises con Manubri",
        "name_en": "Dumbbell Calf Raises",
        "description_it": "In piedi con i manubri, solleva i talloni da terra spingendo sugli avampiedi. Contrai i polpacci in alto e scendi lentamente.",
        "description_en": "Stand with dumbbells, raise heels off ground pushing on balls of feet. Contract calves at top and lower slowly.",
        "muscles_it": "Polpacci (gastrocnemio, soleo)",
        "muscles_en": "Calves (gastrocnemius, soleus)",
        "equipment": "manubri",
        "image": "calf-raises"
    },
    "step-up-manubri": {
        "name_it": "Step-Up con Manubri",
        "name_en": "Dumbbell Step-Ups",
        "description_it": "Con i manubri in mano, sali su una panca o step alto con un piede, poi l'altro. Scendi controllando il movimento.",
        "description_en": "With dumbbells in hands, step up onto bench with one foot, then other. Step down with control.",
        "muscles_it": "Quadricipiti, glutei",
        "muscles_en": "Quads, glutes",
        "equipment": "manubri",
        "image": "step-up-manubri"
    },

    # ==================== STACCHI ====================
    "stacco-da-terra": {
        "name_it": "Stacco da Terra",
        "name_en": "Deadlift",
        "description_it": "Bilanciere a terra, piedi sotto la barra. Afferra il bilanciere, raddrizza la schiena e solleva estendendo le anche e le ginocchia insieme.",
        "description_en": "Barbell on floor, feet under bar. Grip barbell, straighten back and lift by extending hips and knees together.",
        "muscles_it": "Schiena bassa, glutei, femorali, trapezio",
        "muscles_en": "Lower back, glutes, hamstrings, traps",
        "equipment": "bilanciere",
        "image": "stacco-da-terra"
    },
    "stacco-rumeno": {
        "name_it": "Stacco Rumeno",
        "name_en": "Romanian Deadlift",
        "description_it": "In piedi con il bilanciere, abbassalo lungo le gambe piegando le anche e mantenendo le ginocchia leggermente flesse. Risali contraendo glutei e femorali.",
        "description_en": "Stand with barbell, lower it along legs by hinging at hips with slightly bent knees. Rise by contracting glutes and hamstrings.",
        "muscles_it": "Femorali, glutei, schiena bassa",
        "muscles_en": "Hamstrings, glutes, lower back",
        "equipment": "bilanciere",
        "image": "stacco-rumeno"
    },
    "stacco-rumeno-manubri": {
        "name_it": "Stacco Rumeno Manubri",
        "name_en": "Dumbbell Romanian Deadlift",
        "description_it": "In piedi con i manubri, abbassali lungo le gambe piegando le anche. Mantieni la schiena dritta e risali contraendo glutei e femorali.",
        "description_en": "Stand with dumbbells, lower along legs by hinging at hips. Keep back straight and rise by contracting glutes and hamstrings.",
        "muscles_it": "Femorali, glutei",
        "muscles_en": "Hamstrings, glutes",
        "equipment": "manubri",
        "image": "stacco-rumeno"
    },
    "stacco-sumo": {
        "name_it": "Stacco Sumo",
        "name_en": "Sumo Deadlift",
        "description_it": "Piedi molto larghi, punte in fuori, mani tra le gambe sul bilanciere. Solleva il peso estendendo le anche e spingendo le ginocchia in fuori.",
        "description_en": "Wide stance, toes out, hands between legs on barbell. Lift weight extending hips and pushing knees out.",
        "muscles_it": "Glutei, adduttori, quadricipiti",
        "muscles_en": "Glutes, adductors, quads",
        "equipment": "bilanciere",
        "image": "sumo-deadlift"
    },
    "good-morning": {
        "name_it": "Good Morning",
        "name_en": "Good Morning",
        "description_it": "Bilanciere sui trapezi, piega il busto in avanti mantenendo la schiena dritta. Risali contraendo femorali e glutei.",
        "description_en": "Barbell on traps, bend forward keeping back straight. Rise by contracting hamstrings and glutes.",
        "muscles_it": "Femorali, glutei, schiena bassa",
        "muscles_en": "Hamstrings, glutes, lower back",
        "equipment": "bilanciere",
        "image": "good-morning"
    },
    "hip-thrust-bilanciere": {
        "name_it": "Hip Thrust Bilanciere",
        "name_en": "Barbell Hip Thrust",
        "description_it": "Schiena appoggiata su una panca, bilanciere sulle anche. Spingi le anche verso l'alto contraendo i glutei, poi abbassa controllando.",
        "description_en": "Upper back on bench, barbell on hips. Push hips up contracting glutes, then lower with control.",
        "muscles_it": "Glutei, femorali",
        "muscles_en": "Glutes, hamstrings",
        "equipment": "bilanciere",
        "image": "hip-thrust-bilanciere"
    },

    # ==================== SPALLE ====================
    "shoulder-press-manubri": {
        "name_it": "Shoulder Press Manubri",
        "name_en": "Dumbbell Shoulder Press",
        "description_it": "Seduto o in piedi, manubri all'altezza delle spalle. Spingi i pesi sopra la testa estendendo le braccia, poi abbassa controllando.",
        "description_en": "Seated or standing, dumbbells at shoulder height. Push weights overhead extending arms, then lower with control.",
        "muscles_it": "Deltoidi, tricipiti",
        "muscles_en": "Deltoids, triceps",
        "equipment": "manubri",
        "image": "shoulder-press-manubri"
    },
    "military-press": {
        "name_it": "Military Press",
        "name_en": "Military Press",
        "description_it": "In piedi, bilanciere davanti alle spalle. Spingi il peso sopra la testa estendendo completamente le braccia, poi abbassa davanti al petto.",
        "description_en": "Standing, barbell in front of shoulders. Push weight overhead fully extending arms, then lower to chest.",
        "muscles_it": "Deltoidi, tricipiti, core",
        "muscles_en": "Deltoids, triceps, core",
        "equipment": "bilanciere",
        "image": "military-press"
    },
    "arnold-press": {
        "name_it": "Arnold Press",
        "name_en": "Arnold Press",
        "description_it": "Seduto, manubri davanti al viso con palmi verso di te. Ruota i polsi mentre spingi sopra la testa, termina con i palmi in avanti.",
        "description_en": "Seated, dumbbells in front of face with palms facing you. Rotate wrists while pressing overhead, finish with palms forward.",
        "muscles_it": "Deltoidi (tutti i capi), tricipiti",
        "muscles_en": "Deltoids (all heads), triceps",
        "equipment": "manubri",
        "image": "arnold-press"
    },
    "alzate-laterali": {
        "name_it": "Alzate Laterali",
        "name_en": "Lateral Raises",
        "description_it": "In piedi, manubri ai fianchi. Solleva le braccia lateralmente fino all'altezza delle spalle, gomiti leggermente piegati. Abbassa lentamente.",
        "description_en": "Standing, dumbbells at sides. Raise arms laterally to shoulder height, elbows slightly bent. Lower slowly.",
        "muscles_it": "Deltoidi laterali",
        "muscles_en": "Lateral deltoids",
        "equipment": "manubri",
        "image": "alzate-laterali"
    },
    "alzate-frontali": {
        "name_it": "Alzate Frontali",
        "name_en": "Front Raises",
        "description_it": "In piedi, manubri davanti alle cosce. Solleva un braccio alla volta davanti a te fino all'altezza delle spalle, poi abbassa controllando.",
        "description_en": "Standing, dumbbells in front of thighs. Raise one arm at a time in front to shoulder height, then lower with control.",
        "muscles_it": "Deltoidi anteriori",
        "muscles_en": "Front deltoids",
        "equipment": "manubri",
        "image": "alzate-frontali"
    },
    "croci-inverse": {
        "name_it": "Croci Inverse",
        "name_en": "Reverse Flyes",
        "description_it": "Piegato in avanti, braccia pendenti con manubri. Apri le braccia lateralmente portando i manubri all'altezza delle spalle, stringi le scapole.",
        "description_en": "Bent forward, arms hanging with dumbbells. Open arms laterally bringing dumbbells to shoulder height, squeeze shoulder blades.",
        "muscles_it": "Deltoidi posteriori, romboidi",
        "muscles_en": "Rear deltoids, rhomboids",
        "equipment": "manubri",
        "image": "croci-inverse"
    },
    "face-pull": {
        "name_it": "Face Pull",
        "name_en": "Face Pull",
        "description_it": "Al cavo alto con corda, tira verso il viso portando le mani ai lati della testa. Stringi le scapole e ruota esternamente le spalle.",
        "description_en": "At high cable with rope, pull toward face bringing hands to sides of head. Squeeze shoulder blades and externally rotate shoulders.",
        "muscles_it": "Deltoidi posteriori, trapezio, cuffia rotatori",
        "muscles_en": "Rear delts, traps, rotator cuff",
        "equipment": "cavi",
        "image": "face-pull"
    },
    "scrollate-manubri": {
        "name_it": "Scrollate con Manubri",
        "name_en": "Dumbbell Shrugs",
        "description_it": "In piedi, manubri ai fianchi. Solleva le spalle verso le orecchie contraendo il trapezio, mantieni un secondo e abbassa.",
        "description_en": "Standing, dumbbells at sides. Raise shoulders toward ears contracting traps, hold a second and lower.",
        "muscles_it": "Trapezio superiore",
        "muscles_en": "Upper traps",
        "equipment": "manubri",
        "image": "scrollate-manubri"
    },

    # ==================== BICIPITI ====================
    "curl-bilanciere": {
        "name_it": "Curl con Bilanciere",
        "name_en": "Barbell Curls",
        "description_it": "In piedi, bilanciere con presa supina. Piega i gomiti sollevando il peso verso le spalle senza muovere il corpo. Abbassa controllando.",
        "description_en": "Standing, barbell with underhand grip. Bend elbows lifting weight toward shoulders without moving body. Lower with control.",
        "muscles_it": "Bicipiti, avambracci",
        "muscles_en": "Biceps, forearms",
        "equipment": "bilanciere",
        "image": "curl-bilanciere"
    },
    "curl-manubri": {
        "name_it": "Curl con Manubri",
        "name_en": "Dumbbell Curls",
        "description_it": "In piedi o seduto, manubri ai fianchi. Piega un gomito alla volta sollevando il manubrio verso la spalla, poi abbassa e alterna.",
        "description_en": "Standing or seated, dumbbells at sides. Bend one elbow at a time lifting dumbbell toward shoulder, then lower and alternate.",
        "muscles_it": "Bicipiti",
        "muscles_en": "Biceps",
        "equipment": "manubri",
        "image": "curl-manubri"
    },
    "curl-martello": {
        "name_it": "Curl a Martello",
        "name_en": "Hammer Curls",
        "description_it": "In piedi, manubri ai fianchi con presa neutra (pollici in alto). Piega i gomiti sollevando i pesi senza ruotare i polsi.",
        "description_en": "Standing, dumbbells at sides with neutral grip (thumbs up). Bend elbows lifting weights without rotating wrists.",
        "muscles_it": "Bicipiti, brachiale, avambracci",
        "muscles_en": "Biceps, brachialis, forearms",
        "equipment": "manubri",
        "image": "curl-martello"
    },
    "concentration-curl": {
        "name_it": "Curl di Concentrazione",
        "name_en": "Concentration Curls",
        "description_it": "Seduto, gomito appoggiato all'interno della coscia. Piega il gomito sollevando il manubrio verso la spalla, stringi il bicipite in alto.",
        "description_en": "Seated, elbow braced on inner thigh. Bend elbow lifting dumbbell toward shoulder, squeeze bicep at top.",
        "muscles_it": "Bicipiti (picco)",
        "muscles_en": "Biceps (peak)",
        "equipment": "manubri",
        "image": "concentration-curl"
    },
    "preacher-curl": {
        "name_it": "Preacher Curl",
        "name_en": "Preacher Curls",
        "description_it": "Seduto alla panca Scott, braccia appoggiate sul cuscino. Piega i gomiti sollevando il bilanciere, poi abbassa controllando.",
        "description_en": "Seated at preacher bench, arms on pad. Bend elbows lifting barbell, then lower with control.",
        "muscles_it": "Bicipiti (parte inferiore)",
        "muscles_en": "Biceps (lower portion)",
        "equipment": "bilanciere",
        "image": "preacher-curl"
    },

    # ==================== TRICIPITI ====================
    "french-press": {
        "name_it": "French Press",
        "name_en": "Skull Crushers",
        "description_it": "Sdraiato sulla panca, bilanciere sopra il petto. Piega i gomiti abbassando il peso verso la fronte, poi estendi le braccia.",
        "description_en": "Lying on bench, barbell above chest. Bend elbows lowering weight toward forehead, then extend arms.",
        "muscles_it": "Tricipiti",
        "muscles_en": "Triceps",
        "equipment": "bilanciere",
        "image": "french-press"
    },
    "french-press-manubrio": {
        "name_it": "French Press Manubrio",
        "name_en": "Dumbbell Skull Crushers",
        "description_it": "Sdraiato sulla panca, manubri sopra il petto. Piega i gomiti abbassando i pesi ai lati della testa, poi estendi.",
        "description_en": "Lying on bench, dumbbells above chest. Bend elbows lowering weights beside head, then extend.",
        "muscles_it": "Tricipiti",
        "muscles_en": "Triceps",
        "equipment": "manubri",
        "image": "french-press"
    },
    "pushdown-tricipiti": {
        "name_it": "Pushdown Tricipiti",
        "name_en": "Tricep Pushdown",
        "description_it": "Al cavo alto, afferra la barra o corda. Estendi i gomiti spingendo verso il basso, mantieni i gomiti fermi ai fianchi.",
        "description_en": "At high cable, grab bar or rope. Extend elbows pushing down, keep elbows fixed at sides.",
        "muscles_it": "Tricipiti",
        "muscles_en": "Triceps",
        "equipment": "cavi",
        "image": "pushdown-tricipiti"
    },
    "dips-parallele": {
        "name_it": "Dips alle Parallele",
        "name_en": "Parallel Bar Dips",
        "description_it": "Appeso alle parallele, piega i gomiti abbassando il corpo fino a 90°. Spingi per tornare su estendendo le braccia.",
        "description_en": "Hanging on parallel bars, bend elbows lowering body to 90°. Push back up extending arms.",
        "muscles_it": "Tricipiti, pettorali, deltoidi anteriori",
        "muscles_en": "Triceps, chest, front delts",
        "equipment": "parallele",
        "image": "tricep-dips"
    },
    "overhead-tricep-extension": {
        "name_it": "Estensione Tricipiti Sopra la Testa",
        "name_en": "Overhead Tricep Extension",
        "description_it": "In piedi o seduto, manubrio tenuto con entrambe le mani sopra la testa. Piega i gomiti abbassando il peso dietro la testa, poi estendi.",
        "description_en": "Standing or seated, dumbbell held with both hands overhead. Bend elbows lowering weight behind head, then extend.",
        "muscles_it": "Tricipiti (capo lungo)",
        "muscles_en": "Triceps (long head)",
        "equipment": "manubri",
        "image": "overhead-tricep-extension"
    },
}

def get_exercise_with_image(exercise_key: str, sets: int = 3, reps: int = 12, rest: int = 60, duration: int = None) -> dict:
    """
    Restituisce un esercizio completo dal database con set, reps e rest specificati.
    """
    if exercise_key not in GYM_EXERCISES_DATABASE:
        return None
    
    ex = GYM_EXERCISES_DATABASE[exercise_key]
    exercise = {
        "name_it": ex["name_it"],
        "name_en": ex["name_en"],
        "description_it": ex["description_it"],
        "description_en": ex["description_en"],
        "muscles_it": ex["muscles_it"],
        "muscles_en": ex["muscles_en"],
        "equipment": ex["equipment"],
        "image": f"/api/exercises/images/{ex['image']}",
        "sets": sets,
        "rest": rest
    }
    
    if duration:
        exercise["duration"] = duration
    else:
        exercise["reps"] = reps
    
    return exercise
