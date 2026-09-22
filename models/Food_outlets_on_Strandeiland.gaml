/**
* Name: FoodoutletsonStrandeiland
* Agent-Based model made to assess the influence of configurations of food environment on the food consumption of adolescents
 
* Author: jellebiegel
* Tags: 
*/


model Food_outlets_on_Strandeiland

/* Insert your model definition here */

global {


	
	file a1_Street_Strandeiland <- file("../Data/a1.shp");
	shape_file a2_Buildings_Strandeiland <- shape_file("../Data/Scenarios/f0_scenario_400_m_green_realistic.shp");
	shape_file a3_Outline_Strandeiland <- shape_file("../Data/a3_Outline_Strandeiland.shp");
	geometry shape <- envelope(a3_Outline_Strandeiland);
	
	float step <- 30 #sec;
	int nb_adolescents <- 100;
	float exposure_multiplier <- 0.05;
	graph the_graph;
	float visual_halo_radius <- 1500.0 #m;
	
	float min_speed <- 5.0 #km /#h;
	float max_speed <- 15.00 #km /#h;
	
	bool has_saved_data <- false;
	float wtp_upper_limit <- 0.35;
	
	float exposure_radius <- 30 #m;
	float current_run_radius;
	
	float current_lunch_duration <- 45.0;

	string building_type_field <- "Nature";
	
	string export_file_path <- "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/Scenario_5_400_realistic_healthy.csv";
	
	date starting_date <- date([2025, 9, 1 , 7, 0, 0]);
	
	map<string, int> student_diet_tally;
	map<string, int> accumulated_diet_tally <- [];
	map<string, rgb> chart_colors;
	
	reflex count_student_choices {
		map<string, int> temp_tally <- [];
		
		ask adolescents{
			if (food_outlet != nil){
				string current_choice <- food_outlet.type;
				
				if (temp_tally.keys contains current_choice){
					temp_tally[current_choice] <- temp_tally[current_choice] + 1;
				}
				else {
					temp_tally[current_choice] <- 1;
				}
			}
		}
		student_diet_tally <- temp_tally;
	}
	
	reflex record_daily_lunch when: current_date.hour = 12 and current_date.minute = 45 and current_date.second = 0 and current_date.day_of_week <= 5{
		loop choice over: student_diet_tally.keys{
			if (accumulated_diet_tally.keys contains choice){
				accumulated_diet_tally[choice] <- accumulated_diet_tally[choice] + student_diet_tally[choice];
			}
			else{
				accumulated_diet_tally[choice] <- student_diet_tally[choice];
			}
		}
	}
	// This saves the raw, whole-number data at the end of every single simulation world
	reflex export_raw_data when: time >= 7 #days and !has_saved_data {
		
		int school_lunches <- accumulated_diet_tally["School"] != nil ? accumulated_diet_tally["School"] : 0;
		int healthy_lunches <- 0;
		int unhealthy_lunches <- 0;
		
		loop choice over: accumulated_diet_tally.keys {
			if (choice != "School") {
				if (food_health_scores[choice] < 0.0) {
					unhealthy_lunches <- unhealthy_lunches + accumulated_diet_tally[choice];
				} 
			else if (food_health_scores[choice] > 0.0) {
					healthy_lunches <- healthy_lunches + accumulated_diet_tally[choice];
				}
			}
		}
		int total_lunches <- school_lunches
        + healthy_lunches
        + unhealthy_lunches;

    	write "TOTAL LUNCH DECISIONS: " + total_lunches;
		

		// Build the row with semicolons
		string csv_row <- string(seed) + ";" + 
						  string(school_lunches) + ";" + 
						  string(healthy_lunches) + ";" + 
						  string(unhealthy_lunches) + "\n";
						  
		// Append to the raw file
		save csv_row 
			to: export_file_path format: "text" rewrite: false header: false;
		has_saved_data <- true;
	}
	
	list<building> all_food_outlets;
	map<string, float> food_health_scores <- [
		"Fastfood":: -4.5,
		"Grillroom":: -4.5,
		"Sweet shop":: -4.8,
		"Liquor store":: -4.8,
		"Tobacconist":: -4.3,
		"Gas station":: -4.4,
		"Pastry shop":: -4.1,
		"Chocolate shop":: -3.9,
		"Drug store":: -3.4,
		"Ice cream shop":: -3.7,
		"Take-away":: -3.2,
		"Pancake restaurant":: -3.3,
		"Café":: -3.1,
		"Night shop":: -3.0,
		"Café-restaurant":: -2.9,
		"Lunchroom":: -1.6,
		"Cheese store":: -2.2,
		"Restaurant":: -2.2,
		"Butcher":: -1.2,
		"Delicacies shop":: 0.1,
		"Mini mart":: -0.4,
		"Poulterer":: -1.5, 
		"Reform/bio shop":: 2.1,
		"Bakery":: -0.8,
		"Coffee/tea shop":: 0.5,
		"Asian supermarket":: 2.2,
		"Supermarket":: 0.1,
		"Turkish Supermarket":: 2.2,
		"Nut shop":: 2.8,
		"Fish store":: 2.2,
		"Vegetable store":: 4.9
	];
	
	map<string, list<float>> food_price_ranges <- [
		"Fastfood":: [4.0, 10.0],
		"Grillroom":: [5.0, 12.0], // Kapsalon, durum
		"Sweet shop":: [1.0, 4.0],
		"Liquor store":: [5.0, 15.0], // Unlikely lunch spot, priced high
		"Tobacconist":: [1.5, 4.0], // Candy bar, soda
		"Gas station":: [3.5, 8.0], // Overpriced sandwiches
		"Pastry shop":: [2.5, 6.0],
		"Chocolate shop":: [3.0, 8.0],
		"Drug store":: [1.0, 4.0],
		"Ice cream shop":: [1.5, 5.0],
		"Take-away":: [4.0, 12.0],
		"Pancake restaurant":: [8.0, 15.0],
		"Café":: [3.0, 8.0], // Tosti, drink
		"Night shop":: [2.0, 7.0], // Expensive snacks
		"Café-restaurant":: [10.0, 20.0], // Out of budget for most
		"Lunchroom":: [5.0, 12.0],
		"Cheese store":: [8.0, 16.0], // Kaas
		"Restaurant":: [12.0, 30.0], // Out of budget
		"Butcher":: [4.0, 10.0], // Broodje bal, grillworst
		"Delicacies shop":: [4.0, 10.0],
		"Mini mart":: [1.5, 6.0],
		"Poulterer":: [7.0, 12.0], // Chicken wings, nuggets
		"Reform/bio shop":: [3.5, 9.0], // Expensive organic snacks
		"Bakery":: [2.0, 6.0],
		"Coffee/tea shop":: [3.0, 8.0],
		"Asian supermarket":: [1.5, 6.0], // Instant noodles, steamed buns
		"Supermarket":: [1.0, 5.0], // Frikandelbroodje, energy drinks
		"Turkish Supermarket":: [1.0, 5.0], // Lahmacun, Ayran
		"Nut shop":: [2.0, 6.0],
		"Fish store":: [3.0, 8.0], // Kibbeling, haring
		"Vegetable store":: [1.0, 4.0] // Piece of fruit, smoothie
	];
	
	action update_entire_heatmap {
		ask environment_score_grid parallel:true {
			do calculate_cell_score(all_food_outlets, visual_halo_radius);
		}
	}
	
	
	
	init {
		current_run_radius <- exposure_radius;
		loop category over: food_health_scores.keys {
			chart_colors[category] <- rnd_color(255);
		}
		chart_colors["School"] <- #green;
		
		
		create road from: a1_Street_Strandeiland;
		the_graph <- as_edge_graph(road);
		
		create building from: a2_Buildings_Strandeiland with: [type::(read("Nature"))]{
			if (type= "Nature" or type = nil or type = ""){
				type <- "Residential";
			}
			
			if (food_health_scores.keys contains type){
				attractiveness <- food_health_scores[type];
				if (attractiveness < -2.5) { color <- #red;}
				else if (attractiveness < 0){ color<- #orange;}
				else {color <- #green;} 
			
			if (food_price_ranges.keys contains type){
				list<float> range <- food_price_ranges[type];
				price <- rnd(range[0], range[1]);
			}
			else{ 
				price <- rnd(3.0, 8.0);
			}
			}
			if type= "School" {
				color <- #blue ;
				attractiveness <- 5.0;
				price <- rnd(0.0, 5.0);
			}
			
			else if type = "Residential" {
				color <- #gray;
				attractiveness <- 0.0;
				price <- 0.0;
			}
		}
		all_food_outlets <- building where (food_health_scores.keys contains each.type);
		
		list<building> school_building_list <- building where (each.type="School");
		list<building> residential_buildings <- building where (each.type= "Residential");
		
		create adolescents number: nb_adolescents {
			speed <- one_of(min_speed, max_speed);
			start_lunch_hour <- 12;
			start_lunch_minute <- rnd(0,30);
			
			//How much budget//
			float budget_roll <- rnd(100.0);
			if (budget_roll <= 21.2){
				weekly_budget <- rnd(0.0, 5.0);
			}
			else if (budget_roll <= 45.3){
				weekly_budget <- rnd(6.0, 10.0);
			}
			else if (budget_roll <= 61.8){
				weekly_budget <- rnd(11.0, 15.0);
			}
			else if (budget_roll <= 73.2){
				weekly_budget <- rnd(16.0, 20.0);
			}
			else {
				weekly_budget <- rnd(21.0, 35.0); //RIVM research (added 3% of "I don't know to "Weekly budget 20+ euro)//
			}
			
			//Probability of not eating its own lunch//
			
			float frequency_roll <- rnd(100.0);
			if (frequency_roll <= 40.0) {
				base_buy_probability <- 0.0;
			} 
			else if (frequency_roll <= 64.0) { 
				base_buy_probability <- 0.1;
			} 
			else if (frequency_roll <= 80.0) { 
				base_buy_probability <- 0.2;
			} 
			else if (frequency_roll <= 90.0) { 
				base_buy_probability <- 0.4;
			} 
			else if (frequency_roll <= 96.0) { 
				base_buy_probability <- 0.6;
			} 
			else if (frequency_roll <= 98.0) { 
				base_buy_probability <- 0.8;
			} 
			else {
				base_buy_probability <- 1.0;
			}
			
			buy_lunch_probability <- base_buy_probability;
			
			max_lunch_duration_seconds<- current_lunch_duration * 60;
			school_building <- one_of(school_building_list);
			food_outlet <- school_building;
			
			home_building<- one_of(residential_buildings);
		
			objective <- "At Home";
			location <- any_location_in (home_building);
		}
	 
		do update_entire_heatmap;	
	}
}

species building {
	string type;
	rgb color <- #gray;
	
	float attractiveness;
	float price;
	
	aspect base{
		if (type= "Fastfood"){
		draw shape color: color border:#black depth: 15.0;
		}
		else if (type= "School"){
		draw shape color: color border: #black depth: 15.0;
		}
		else if (type= "Supermarket"){
		draw shape color: color border: #black depth: 16;
		}
		else {
		draw shape color: color border: #black ;
		}
	}
}
species road{
	rgb color <- #blue;
	
	aspect base{
		draw shape color:color width: 2.0;
	}
}

grid environment_score_grid cell_width: 50#m cell_height: 50#m{
	float intensity <- 0.0;
	float occupancy <- 0.0;
	float total_score <- 0.0;
	
	
action calculate_cell_score(list<building> outlets, float radius){
	list<building> shops_in_range <- outlets where ((each.location distance_to self.location) <= radius);
	
	if (empty(shops_in_range)){
		intensity <- 0.0;
		occupancy <- 0.0;
		total_score <- 0.0;
		color <- #white;
		
	}
	else{
		float sum_weighted_scores <- 0.0;
		float sum_weights <- 0.0;
		float prob_not_seeing <- 1.0;
	
		ask shops_in_range {
			float dist <- self.location distance_to myself.location;
			float k_d <- (1.0 - (dist / radius)^2)^2;
			
			if (dist > radius) { k_d <- 1e-10; 
			}
			sum_weighted_scores <- sum_weighted_scores + (self.attractiveness * k_d);
			sum_weights <- sum_weights + k_d;
			prob_not_seeing <- prob_not_seeing * (1.0 - k_d);	
		}
		intensity <- sum_weights > 0 ? (sum_weighted_scores / sum_weights) : 0.0;
		occupancy <- 1.0 - prob_not_seeing;
		total_score <- occupancy* intensity;
		
		if (total_score < 0) { 
                // Blends from Red (-5) to Orange (0)
                color <- blend(#orange, #red, (total_score + 5.0) / 5.0); 
            } 
            else if (total_score > 0) { 
                // Blends from Orange (0) to Green (+5)
                color <- blend(#green, #orange, total_score / 5.0); 
            } 
            else { 
                color <- #orange; 
            } 
        } 
    }
    aspect text_overlay {
        // 1. Draw the background color of the cell
        draw shape color: color border: #darkgray;
        
        // 2. Overlay the numerical score
        // We check if the color is not white to ensure we don't draw 0.0 on empty map areas
        if (color != #white) {
            draw string(total_score with_precision 1) 
                at: location 
                color: #black 
                font: font("Helvetica", 10, #bold);
        }
    }

}


//////////////////////////////////////////////Adolescent species//////////////////////////////////////////////////


species adolescents skills: [moving]{
	rgb color <- #yellow;
	building school_building <- nil;
	building food_outlet <- nil;
	building home_building <- nil;
	
	int start_lunch_hour;
	int start_lunch_minute;
	
	float max_lunch_duration_seconds;
	float time_spent_on_lunch;
	float eating_time <- rnd(4 #mn,9#mn);
	
	//Budget and behaviour//
	float weekly_budget;
	float daily_spending_limit;
	float buy_lunch_probability;
	float base_buy_probability;
	
	//BST cognitive variables//
	float food_cue_susceptibility <- rnd(0.0, 1.0);
	float daily_junk_exposure <- 0.0;
	
	
	string objective;
	point the_target <- nil;
	
	// The action that allows the agents to make a decision on where to eat//
	action make_lunch_decision{
		daily_spending_limit <- weekly_budget * rnd(0.15, wtp_upper_limit); //random number for WTP (NO ACADEMIC FOUNDATION)//
		list<building> reachable_shops <- all_food_outlets where (
			(((self distance_to each)/ speed) * 2 + eating_time < max_lunch_duration_seconds)
			and
			(((self distance_to each)/ speed) <= 9 #mn)
			and
			(each.price <= daily_spending_limit));
				
		write "lunch time: " + (max_lunch_duration_seconds / 60) + " mins | reachable shops: " + length(reachable_shops);
		if (!empty(reachable_shops)) {
			food_outlet <- reachable_shops with_max_of(((5.0 - each.attractiveness) / (self distance_to each)) * rnd(0.5, 1.5));//adding randomness to adhere to taste "ergens zin in hebben"//
			the_target <- any_location_in(food_outlet);
			weekly_budget <- weekly_budget-food_outlet.price;
		}
		else{
			food_outlet<- school_building;
			the_target<- any_location_in(school_building);
		}
	}
	
	
	//Reflex School schedule//
	
	reflex go_to_school when: current_date.hour = 8 and current_date.minute = 0 and current_date.day_of_week <= 5 and objective = "At Home" {
		objective <- "Going to School";
		the_target <- any_location_in(school_building);
		daily_junk_exposure <- 0.0;
	}
	
	reflex arrive_at_school when: objective= "Going to School" and the_target = nil {
		objective <- "At School";
	}
	
	reflex go_home when: current_date.hour = 15 and current_date.minute = 30 and current_date.day_of_week <=5 {
		if (objective = "At School" or objective = "Eating Packed Lunch"){
			objective <- "Going Home";
			the_target <- any_location_in(home_building);
		}
	}
	
	reflex arrive_home when: objective = "Going Home" and the_target= nil {
		objective <- "At Home";
	}
	
	// Reflex for when "time to lunch"//
	reflex time_to_lunch when: current_date.hour = start_lunch_hour and current_date.minute = start_lunch_minute and objective = "At School"{
		float impulse_boost <- daily_junk_exposure * food_cue_susceptibility;
		buy_lunch_probability <- min ([1.0, base_buy_probability + impulse_boost]);
		if (flip(buy_lunch_probability)){
		objective <- "Getting Lunch";
		time_spent_on_lunch <- 0.0;
		do make_lunch_decision;
		}
		else{
			objective <- "Eating Packed Lunch";
			time_spent_on_lunch <- 0.0;
			food_outlet<- school_building;
			the_target <- any_location_in(school_building);
		}
	}
	
	reflex count_packed_lunch_time when: objective = "Eating Packed Lunch" {
		time_spent_on_lunch <- time_spent_on_lunch + step;
		if (time_spent_on_lunch >= max_lunch_duration_seconds) {
			objective <- "At School";
		}
	}
	
	reflex count_lunch_time when: objective = "Getting Lunch"{
		time_spent_on_lunch <- time_spent_on_lunch + step;
	}
	
	reflex time_to_school when: time_spent_on_lunch >= max_lunch_duration_seconds and objective = "Getting Lunch" {
		objective <- "At School";
		the_target <- any_location_in(school_building);
	}
	
	reflex weekly_allowance when: current_date.day_of_week = 1 and current_date.hour = 8 and current_date.minute = 0{
		float budget_roll <- rnd(100.0);
			if (budget_roll <= 21.2){
				weekly_budget <- rnd(0.0, 5.0);
			}
			else if (budget_roll <= 45.3){
				weekly_budget <- rnd(6.0, 10.0);
			}
			else if (budget_roll <= 61.8){
				weekly_budget <- rnd(11.0, 15.0);
			}
			else if (budget_roll <= 73.2){
				weekly_budget <- rnd(16.0, 20.0);
			}
			else {
				weekly_budget <- rnd(21.0, 35.0); //RIVM research (added 3% of "I don't know to "Weekly budget 20+ euro)//
			} 
	}
	reflex move when: the_target != nil{
		do goto target: the_target on: the_graph;
		list<building> nearby_shops <- all_food_outlets at_distance exposure_radius;
		if (!empty(nearby_shops)){
			
			ask nearby_shops{
				
				float dist <- myself distance_to self;
				float k_d <- 1.0 - (dist / exposure_radius);
				
				if (flip(k_d)) {
					
					myself.daily_junk_exposure <- myself.daily_junk_exposure + (1.0 * exposure_multiplier);
					 
				}
			}
			daily_junk_exposure <- max([0.0, daily_junk_exposure]);
		}
		float exposure_ratio <- min([1.0, daily_junk_exposure / 1.5 ]);
		if (exposure_ratio <= 0.5){
			color<- blend (#yellow, #green, exposure_ratio * 2.0);
		}
		else{
			color <- blend(#red, #yellow, (exposure_ratio - 0.5)*2.0);
		}
		if the_target = location {
			the_target <- nil;
		}
	}
	
	aspect base{
		draw circle(10) color:color border: #black;
	}
	
}

experiment food_environment{
	parameter "Shapefile for the buildings" var: a2_Buildings_Strandeiland category: "GIS" ;
	parameter "Shapefile for the roads" var: a1_Street_Strandeiland category: "GIS" ;
	parameter "Shapefile for the bounds" var: a3_Outline_Strandeiland category: "GIS" ;
	parameter "Number of adolescents" var: nb_adolescents category: "Adolescents";
	parameter "minimal speed" var: min_speed category: "People" min: 5 #km/#h;
	parameter "maximal speed" var: max_speed category: "People" max: 15 #km/#h;
	
	action change_building_type {
		ask world { // This tells the UI to interact with the main map
			point clicked_point <- #user_location;
			list<building> clicked_buildings <- building overlapping clicked_point;
			
			if (!empty(clicked_buildings)) {
				building target_building <- clicked_buildings[0];
				
				list<string> available_options <- food_health_scores.keys + ["Residential", "Cancel"];
				
				map<string, unknown> result <- user_input_dialog("Change Zoning Law for this building", [
				choose("New Shop Type", string, "Cancel", available_options)
				]);
				
				if (result != nil and !empty(result)){
					string chosen_type <- string(result["New Shop Type"]);
					
					if (chosen_type != "Cancel") {
						
						ask target_building {
							type <- chosen_type;
							
							if (food_health_scores.keys contains type) {
								attractiveness <- food_health_scores[type];
								if (attractiveness < -2.5) { color <- #red; }
								else if (attractiveness < 0.0) { color <- #orange; }
								else { color <- #green; } 
								
								if (food_price_ranges.keys contains type) {
									list<float> range <- food_price_ranges[type];
									price <- rnd(range[0], range[1]);
								}
							} else if (type = "Residential") {
								color <- #gray;
								attractiveness <- 0.0;
								price <- 0.0;
						}
					}
				
					// Update global list
					all_food_outlets <- building where (food_health_scores.keys contains each.type);
					do update_entire_heatmap;
					write "User Intervention: Building changed to " + chosen_type;
					
					}
				}
			}
		}
	}
	
	output{
		
		display strandeiland_display type: 2d {
			species road aspect: base;
			species building aspect: base;
			species adolescents aspect: base trace: false;
			
			event #mouse_down action: change_building_type;
			
			
			}
		
		display "Dietary choices" type:2d{
			chart "Where are students eating?" type: pie{
				datalist legend: student_diet_tally.keys value:student_diet_tally.values color: student_diet_tally.keys collect (chart_colors[each]);
				
			}
		}	
		display "RIVM Food Pressure Map" type: 2d {
			grid environment_score_grid;
			species environment_score_grid aspect: text_overlay;
			species road aspect: base;
			species building aspect: base;
			species adolescents aspect: base;
			
		}
	}
}
experiment sensitivity_analysis_exposure type:batch repeat: 5 until: (time>7 #days){
	parameter "Exposure Multiplier" var: exposure_multiplier min: 0.01 max: 0.10 step: 0.01;
	
	reflex save_results when: time >= 7#days{
		string csv_row <- string(exposure_multiplier with_precision 2);
		
		loop choice over: accumulated_diet_tally.keys{
			csv_row <- csv_row + "," + choice + "," + string(accumulated_diet_tally[choice]);
		}
		save csv_row
			to: "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/sensitivity_exposure_results.csv" format: "csv" rewrite: false header: false;
			
	}
}



experiment sensitivity_analysis_exposure_heavy type: batch repeat: 5 until: (time >= 7 #days) {
	parameter "Exposure Multiplier" var: exposure_multiplier min: 0.01 max: 0.10 step: 0.01;
	
	init{ 
		string header <- "Exposure Multiplier;School Lunch;Health Lunches;Unhealthy Lunches\n";
		save header to: "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/health_50_raw.csv" format: "text" rewrite: true;
	}
}

experiment sensitivity_analysis_spending type: batch repeat: 5 until: (time >= 7 #days) {
	parameter "WTP Upper Limit" var: wtp_upper_limit min: 0.20 max: 0.80 step: 0.10;
	
	init { 
		string header <- "WTP Upper Limit;School Lunch;Health Lunches;Unhealthy Lunches\n";
		save header to: "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/spending_50_raw.csv" format: "text" rewrite: true;
	}
}

experiment sensitivity_analysis_radius type: batch repeat: 5 until: (time >= 7 #days) {
	parameter "Exposure Radius" var: exposure_radius min: 10.0 max: 60.0 step: 10.0;
	
	init { 
		string header <- "Exposure Radius;School Lunch;Health Lunches;Unhealthy Lunches\n";
		save header to: "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/radius_50_raw.csv" format: "text" rewrite: true;
	}
}

experiment sensitivity_analysis_speed type: batch repeat: 5 until: (time >= 7 #days) {
	parameter "Max Speed (Mobility)" var: max_speed min: 5.0 #km/#h max: 30.0 #km/#h step: 5.0 #km/#h;
	
	init { 
		string header <- "Max Speed;School Lunch;Healthy Lunches;Unhealthy Lunches\n";
		save header to: "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/speed_raw.csv" format: "text" rewrite: true;
	}
}
experiment sensitivity_analysis_duration type: batch repeat: 5 until: (time >= 7 #days) {
	parameter "Lunch Duration (mins)" var: current_lunch_duration min: 5.0 max: 15.0 step: 5.0;
	
	init { 
		string header <- "Lunch Duration;School Lunch;Healthy Lunches;Unhealthy Lunches\n";
		save header to: "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/duration_raw_all_reps.csv" format: "text" rewrite: true;
	}
}

experiment Baseline_Stress_Test type: batch repeat: 1 until: (time > 7 #days) {

    parameter "Lunch Duration (mins)" var: current_lunch_duration <- 30.0;
    parameter "Exposure Radius" var: exposure_radius <- 30.0 #m;
    parameter "Exposure Multiplier" var: exposure_multiplier <- 0.10;
    parameter "WTP Upper Limit" var: wtp_upper_limit <- 0.35;

    parameter "Export Path" var: export_file_path <- "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/headless_test.csv";

    init {
        string header <- "Seed;School_Lunches;Healthy_Lunches;Unhealthy_Lunches\n";

        save header to: export_file_path
            format: "text"
            rewrite: true;
    }
}
experiment Scenario_1_400_meters type: batch repeat: 20 until: (time >= 7 #days) {
	
	// 1. HARDCODE THE SCENARIO 0 PARAMETERS
	parameter "Lunch Duration (mins)" var: current_lunch_duration <- 30.0;
	parameter "Exposure Radius" var: exposure_radius <- 30.0 #m;
	parameter "Exposure Multiplier" var: exposure_multiplier <- 0.10;
	parameter "WTP Upper Limit" var: wtp_upper_limit <- 0.35;
	
	// 2. HIJACK THE GLOBAL SAVE PATH
	parameter "Export Path" var: export_file_path <- "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/Scenario_1_400_meter.csv";
	
	// 3. CREATE THE CLEAN FILE AND HEADER BEFORE RUNNING
	init { 
		string header <- "Seed;School_Lunches;Healthy_Lunches;Unhealthy_Lunches\n";
		save header to: "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/Scenario_1_400_meter.csv" format: "text" rewrite: true;
	}
}

experiment Scenario_2_Cluster_away type: batch repeat: 20 until: (time >= 7 #days) {
	
	// 1. HARDCODE THE SCENARIO 0 PARAMETERS
	parameter "Lunch Duration (mins)" var: current_lunch_duration <- 30.0;
	parameter "Exposure Radius" var: exposure_radius <- 30.0 #m;
	parameter "Exposure Multiplier" var: exposure_multiplier <- 0.10;
	parameter "WTP Upper Limit" var: wtp_upper_limit <- 0.35;
	
	// 2. HIJACK THE GLOBAL SAVE PATH
	parameter "Export Path" var: export_file_path <- "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/Scenario_2_Cluster_away.csv";
	
	// 3. CREATE THE CLEAN FILE AND HEADER BEFORE RUNNING
	init { 
		string header <- "Seed;School_Lunches;Healthy_Lunches;Unhealthy_Lunches\n";
		save header to: "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/Scenario_2_Cluster_away.csv" format: "text" rewrite: true;
	}
}
experiment Scenario_3_Cluster_Close type: batch repeat: 20 until: (time >= 7 #days) {
	
	// 1. HARDCODE THE SCENARIO 0 PARAMETERS
	parameter "Lunch Duration (mins)" var: current_lunch_duration <- 30.0;
	parameter "Exposure Radius" var: exposure_radius <- 30.0 #m;
	parameter "Exposure Multiplier" var: exposure_multiplier <- 0.10;
	parameter "WTP Upper Limit" var: wtp_upper_limit <- 0.35;
	
	// 2. HIJACK THE GLOBAL SAVE PATH
	parameter "Export Path" var: export_file_path <- "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/Scenario_3_Cluster_close.csv";
	
	// 3. CREATE THE CLEAN FILE AND HEADER BEFORE RUNNING
	init { 
		string header <- "Seed;School_Lunches;Healthy_Lunches;Unhealthy_Lunches\n";
		save header to: "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/Scenario_3_Cluster_close.csv" format: "text" rewrite: true;
	}
}
experiment Scenario_4_400_meter_green type: batch repeat: 20 until: (time >= 7 #days) {
	
	// 1. HARDCODE THE SCENARIO 0 PARAMETERS
	parameter "Lunch Duration (mins)" var: current_lunch_duration <- 30.0;
	parameter "Exposure Radius" var: exposure_radius <- 30.0 #m;
	parameter "Exposure Multiplier" var: exposure_multiplier <- 0.10;
	parameter "WTP Upper Limit" var: wtp_upper_limit <- 0.35;
	
	// 2. HIJACK THE GLOBAL SAVE PATH
	parameter "Export Path" var: export_file_path <- "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/Scenario_4_400_meter_green.csv";
	
	// 3. CREATE THE CLEAN FILE AND HEADER BEFORE RUNNING
	init { 
		string header <- "Seed;School_Lunches;Healthy_Lunches;Unhealthy_Lunches\n";
		save header to: "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/Scenario_4_400_meter_green.csv" format: "text" rewrite: true;
	}
}
experiment Scenario_5_400_meter_realistic_healthy type: batch repeat: 20 until: (time >= 7 #days) {
	
	// 1. HARDCODE THE SCENARIO 0 PARAMETERS
	parameter "Lunch Duration (mins)" var: current_lunch_duration <- 30.0;
	parameter "Exposure Radius" var: exposure_radius <- 30.0 #m;
	parameter "Exposure Multiplier" var: exposure_multiplier <- 0.10;
	parameter "WTP Upper Limit" var: wtp_upper_limit <- 0.35;
	
	// 2. HIJACK THE GLOBAL SAVE PATH
	parameter "Export Path" var: export_file_path <- "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/Scenario_5_400_realistic_healthy.csv";
	
	// 3. CREATE THE CLEAN FILE AND HEADER BEFORE RUNNING
	init { 
		string header <- "Seed;School_Lunches;Healthy_Lunches;Unhealthy_Lunches\n";
		save header to: "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/Scenario_5_400_realistic_healthy.csv" format: "text" rewrite: true;
	}
}
experiment web_experiment {
	parameter "Building type field"
		var: building_type_field;

	parameter "Roads shapefile"
		var: a1_Street_Strandeiland;
		
	parameter "Boundary shapefile"
		var: a3_Outline_Strandeiland;
		
    parameter "Building shapefile"
    	var: a2_Buildings_Strandeiland;
    	
    parameter "Lunch Duration (mins)"
        var: current_lunch_duration <- 30.0;

    parameter "Exposure Radius"
        var: exposure_radius <- 30.0 #m;

    parameter "Exposure Multiplier"
        var: exposure_multiplier <- 0.10;

    parameter "WTP Upper Limit"
        var: wtp_upper_limit <- 0.35;

    parameter "Export Path"
        var: export_file_path <-
        "/Users/jellebiegel/Documents/Thesis/Thesis_Strandeiland/Results/web_test.csv";

    init {
        string header <- "Seed;School_Lunches;Healthy_Lunches;Unhealthy_Lunches\n";

        save header to: export_file_path
            format: "text"
            rewrite: true;
    }
}